import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.apps.accounts.models import Subject
from config.apps.chat_app.models import ChatRoom
from config.apps.block.utils import users_have_block_relation

from .models import (
    CommissionInvoice,
    StudentPaybackAccount,
    TutoringRegistration,
    TutoringResource,
    TutoringResourceFile,
    TutoringSubmission,
)


class RegistrationPermissionError(Exception):
    pass


def participant_role(chat_room, user):
    if chat_room.student.user_id == user.id:
        return TutoringSubmission.Role.STUDENT
    if chat_room.instructor.user_id == user.id:
        return TutoringSubmission.Role.INSTRUCTOR
    raise RegistrationPermissionError("해당 채팅방의 참여자만 이용할 수 있습니다.")


def get_chat_room_for_user(chat_room_id, user, lock=False):
    queryset = ChatRoom.objects.select_related(
        "student__user", "instructor__user"
    )
    if lock:
        queryset = queryset.select_for_update()
    room = queryset.filter(pk=chat_room_id).first()
    if room is None:
        return None, None
    role = participant_role(room, user)
    counterpart = (
        room.instructor.user
        if role == TutoringSubmission.Role.STUDENT
        else room.student.user
    )
    if users_have_block_relation(user, counterpart):
        raise RegistrationPermissionError("차단 관계인 사용자의 과외 등록에 접근할 수 없습니다.")
    return room, role


def _fernet():
    configured_key = getattr(settings, "TUTORING_ACCOUNT_ENCRYPTION_KEY", "")
    if configured_key:
        key = configured_key.encode()
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_account_number(account_number):
    return _fernet().encrypt(account_number.encode()).decode()


def decrypt_account_number(encrypted_account_number):
    return _fernet().decrypt(encrypted_account_number.encode()).decode()


def _submission_comparison(registration):
    submissions = {
        submission.role: submission
        for submission in registration.submissions.all()
    }
    student = submissions.get(TutoringSubmission.Role.STUDENT)
    instructor = submissions.get(TutoringSubmission.Role.INSTRUCTOR)
    if not student or not instructor:
        return student, instructor, []

    mismatched_fields = []
    if student.class_type != instructor.class_type:
        mismatched_fields.append("classType")
    if student.first_month_fee != instructor.first_month_fee:
        mismatched_fields.append("firstMonthFee")
    return student, instructor, mismatched_fields


def _compare_submissions(registration):
    student, instructor, mismatched_fields = _submission_comparison(registration)

    if not student or not instructor:
        registration.attribute_validation_status = (
            TutoringRegistration.AttributeValidationStatus.UNCHECKED
        )
        registration.confirmed_class_type = ""
        registration.confirmed_first_month_fee = None
        registration.terms_confirmed_at = None
        return student, instructor, []

    if mismatched_fields:
        registration.attribute_validation_status = (
            TutoringRegistration.AttributeValidationStatus.MISMATCHED
        )
        registration.confirmed_class_type = ""
        registration.confirmed_first_month_fee = None
        registration.terms_confirmed_at = None
    else:
        registration.attribute_validation_status = (
            TutoringRegistration.AttributeValidationStatus.MATCHED
        )
        registration.confirmed_class_type = instructor.class_type
        registration.confirmed_first_month_fee = instructor.first_month_fee
        registration.terms_confirmed_at = timezone.now()
    return student, instructor, mismatched_fields


def commission_rate_bps(class_type):
    if class_type == TutoringSubmission.ClassType.SHORT_TERM:
        return getattr(settings, "TUTORING_SHORT_TERM_COMMISSION_RATE_BPS", 700)
    return getattr(settings, "TUTORING_REGULAR_COMMISSION_RATE_BPS", 1500)


def class_type_label(class_type):
    if class_type == TutoringSubmission.ClassType.SHORT_TERM:
        return "단기 수업"
    return "장기 수업"


def refresh_contract_status(registration):
    student, instructor, _ = _submission_comparison(registration)
    invoice = registration.commission_invoices.filter(
        invoice_type=CommissionInvoice.InvoiceType.INITIAL
    ).first()

    if not student or not instructor:
        status_value = TutoringRegistration.ContractStatus.COLLECTING
    elif (
        registration.attribute_validation_status
        == TutoringRegistration.AttributeValidationStatus.MATCHED
        and invoice is not None
        and invoice.status == CommissionInvoice.Status.PAID
    ):
        status_value = TutoringRegistration.ContractStatus.ACTIVE
    else:
        status_value = TutoringRegistration.ContractStatus.REGISTERED

    if registration.contract_status != status_value:
        registration.contract_status = status_value
        registration.save(update_fields=["contract_status", "updated_at"])
    return status_value


def _replace_proof_files(resource, proof_files):
    for stored_file in resource.files.all():
        stored_file.file.delete(save=False)
        stored_file.delete()
    for uploaded_file in proof_files:
        TutoringResourceFile.objects.create(
            tutoring_resource=resource,
            file=uploaded_file,
        )


def _sync_resource(
    registration,
    room,
    student_submission,
    instructor_submission,
    subject_ids,
    proof_files,
):
    resource, _ = TutoringResource.objects.select_for_update().get_or_create(
        registration=registration,
        defaults={
            "student": room.student,
            "instructor": room.instructor,
        },
    )
    preferred_submission = instructor_submission or student_submission
    resource.student = room.student
    resource.instructor = room.instructor
    resource.start_date = registration.start_date
    resource.class_type = (
        class_type_label(preferred_submission.class_type)
        if preferred_submission
        else ""
    )
    resource.first_month_fee = (
        preferred_submission.first_month_fee if preferred_submission else None
    )
    resource.is_student_confirmed = student_submission is not None
    resource.is_instructor_confirmed = instructor_submission is not None
    resource.save()

    if subject_ids:
        resource.subject.set(Subject.objects.filter(number__in=subject_ids))

    if proof_files:
        _replace_proof_files(resource, proof_files)

    invoice = registration.commission_invoices.filter(
        invoice_type=CommissionInvoice.InvoiceType.INITIAL
    ).first()
    if invoice is None:
        resource.fee_payment_status = "PENDING"
    elif invoice.status == CommissionInvoice.Status.PAID:
        resource.fee_payment_status = "PAID"
    elif invoice.status == CommissionInvoice.Status.FAILED:
        resource.fee_payment_status = "FAILED"
    else:
        resource.fee_payment_status = "AWAITING_CONFIRMATION"
    resource.save(update_fields=["fee_payment_status"])
    return resource


def save_my_registration(
    chat_room_id,
    user,
    validated_data,
    proof_files=(),
):
    """현재 사용자의 독립 제출과 수동 입금 검증 정보를 원자적으로 저장한다."""
    with transaction.atomic():
        room, role = get_chat_room_for_user(chat_room_id, user, lock=True)
        if room is None:
            return None

        registration, _ = (
            TutoringRegistration.objects.select_for_update().get_or_create(
                chat_room=room,
                defaults={
                    "student": room.student.user,
                    "instructor": room.instructor.user,
                    "subject": validated_data["subject"],
                    "start_date": validated_data["start_date"],
                },
            )
        )
        registration.subject = validated_data["subject"]
        registration.start_date = validated_data["start_date"]

        TutoringSubmission.objects.update_or_create(
            registration=registration,
            role=role,
            defaults={
                "submitted_by": user,
                "class_type": validated_data["class_type"],
                "first_month_fee": validated_data["first_month_fee"],
            },
        )

        if role == TutoringSubmission.Role.STUDENT:
            account = validated_data["payback_account"]
            StudentPaybackAccount.objects.update_or_create(
                registration=registration,
                defaults={
                    "bank_code": account["bank_code"],
                    "encrypted_account_number": encrypt_account_number(
                        account["account_number"]
                    ),
                    "account_holder": account["account_holder"],
                    "verification_status": (
                        StudentPaybackAccount.VerificationStatus.UNVERIFIED
                    ),
                    "verified_at": None,
                },
            )

        registration.refresh_from_db()
        previous_validation_status = registration.attribute_validation_status
        student_submission, instructor_submission, mismatched_fields = (
            _compare_submissions(registration)
        )
        registration.save()

        if (
            registration.attribute_validation_status
            == TutoringRegistration.AttributeValidationStatus.MISMATCHED
            and previous_validation_status
            != TutoringRegistration.AttributeValidationStatus.MISMATCHED
        ):
            # MISMATCHED 전환 시 1회만 양측에 알림 (반복 제출 시 중복 방지)
            from config.apps.notification.helpers import (
                notify_registration_mismatched,
            )

            notify_registration_mismatched(registration)

        invoice = None
        if role == TutoringSubmission.Role.INSTRUCTOR:
            rate_bps = commission_rate_bps(instructor_submission.class_type)
            commission_amount = (
                instructor_submission.first_month_fee * rate_bps // 10000
            )
            invoice, _ = CommissionInvoice.objects.update_or_create(
                registration=registration,
                invoice_type=CommissionInvoice.InvoiceType.INITIAL,
                defaults={
                    "base_amount": instructor_submission.first_month_fee,
                    "commission_rate_bps": rate_bps,
                    "commission_amount": commission_amount,
                    "status": CommissionInvoice.Status.PAYMENT_PENDING,
                    "paid_at": None,
                },
            )

        resource = _sync_resource(
            registration,
            room,
            student_submission,
            instructor_submission,
            validated_data.get("subject_ids", []),
            proof_files,
        )
        previous_contract_status = registration.contract_status
        contract_status = refresh_contract_status(registration)
        if (
            contract_status == TutoringRegistration.ContractStatus.ACTIVE
            and previous_contract_status
            != TutoringRegistration.ContractStatus.ACTIVE
        ):
            from config.apps.notification.helpers import (
                notify_fee_payment_confirmed,
            )

            notify_fee_payment_confirmed(resource)

        if invoice is None:
            invoice = registration.commission_invoices.filter(
                invoice_type=CommissionInvoice.InvoiceType.INITIAL
            ).first()

        return {
            "registration": registration,
            "resource": resource,
            "invoice": invoice,
            "role": role,
            "mismatched_fields": mismatched_fields,
        }


def serialize_payment(invoice):
    if invoice is None:
        return None
    return {
        "invoiceId": invoice.pk,
        "amount": invoice.commission_amount,
        "commissionRateBps": invoice.commission_rate_bps,
        "status": invoice.status,
        "bank": settings.TUTORING_PAYMENT_BANK,
        "accountNumber": settings.TUTORING_PAYMENT_ACCOUNT_NUMBER,
        "paidAt": invoice.paid_at,
    }


def serialize_registration(registration, user, role=None, mismatched_fields=None):
    if role is None:
        role = (
            TutoringSubmission.Role.STUDENT
            if registration.student_id == user.id
            else TutoringSubmission.Role.INSTRUCTOR
        )
    submissions = {
        submission.role: submission
        for submission in registration.submissions.all()
    }
    mine = submissions.get(role)
    counterparty_role = (
        TutoringSubmission.Role.INSTRUCTOR
        if role == TutoringSubmission.Role.STUDENT
        else TutoringSubmission.Role.STUDENT
    )
    counterparty = submissions.get(counterparty_role)
    if mismatched_fields is None:
        _, _, mismatched_fields = _submission_comparison(registration)

    resource = getattr(registration, "resource", None)
    data = {
        "registrationId": registration.pk,
        "resourceId": resource.pk if resource else None,
        "chatRoomId": registration.chat_room_id,
        "subject": registration.subject,
        "startDate": registration.start_date,
        "student": {
            "id": registration.student_id,
            "userName": registration.student.user_name,
        },
        "instructor": {
            "id": registration.instructor_id,
            "userName": registration.instructor.user_name,
        },
        "attributeValidationStatus": registration.attribute_validation_status,
        "contractStatus": registration.contract_status,
        "studentSubmitted": TutoringSubmission.Role.STUDENT in submissions,
        "instructorSubmitted": TutoringSubmission.Role.INSTRUCTOR in submissions,
        "mySubmission": None,
        "counterpartySubmission": {"submitted": counterparty is not None},
    }
    if mine:
        data["mySubmission"] = {
            "role": mine.role,
            "classType": mine.class_type,
            "firstMonthFee": mine.first_month_fee,
            "submittedAt": mine.updated_at,
        }
    if (
        registration.attribute_validation_status
        == TutoringRegistration.AttributeValidationStatus.MISMATCHED
    ):
        data["mismatchedFields"] = mismatched_fields
    return data

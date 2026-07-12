import base64
import hashlib
import hmac
import uuid

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from config.apps.chat_app.models import ChatRoom

from .models import (
    CommissionInvoice,
    StudentPaybackAccount,
    TutoringRegistration,
    TutoringSubmission,
    VirtualAccountPayment,
)


COMMISSION_RATES = {
    TutoringSubmission.ClassType.REGULAR: 1500,
    TutoringSubmission.ClassType.SHORT_TERM: 700,
}

BANK_NAMES = {
    "03": "기업은행",
    "04": "국민은행",
    "11": "농협은행",
    "20": "우리은행",
    "23": "SC제일은행",
    "31": "대구은행",
    "32": "부산은행",
    "34": "광주은행",
    "35": "제주은행",
    "37": "전북은행",
    "39": "경남은행",
    "71": "우체국",
    "81": "하나은행",
    "88": "신한은행",
}


class RegistrationPermissionError(Exception):
    pass


class VirtualAccountIssueError(Exception):
    def __init__(self, message, payload=None):
        super().__init__(message)
        self.payload = payload or {"message": message}


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
    return room, participant_role(room, user)


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


def _submission_comparison(registration):
    submissions = {submission.role: submission for submission in registration.submissions.all()}
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
        registration.contract_status = TutoringRegistration.ContractStatus.COLLECTING
        registration.confirmed_class_type = ""
        registration.confirmed_first_month_fee = None
        registration.terms_confirmed_at = None
        return []

    registration.contract_status = TutoringRegistration.ContractStatus.REGISTERED
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
    return mismatched_fields


def save_my_registration(chat_room_id, user, validated_data):
    """DB 변경을 완료하고, 트랜잭션 밖에서 발급할 결제 객체를 반환한다."""
    with transaction.atomic():
        room, role = get_chat_room_for_user(chat_room_id, user, lock=True)
        if room is None:
            return None

        registration, _ = TutoringRegistration.objects.select_for_update().get_or_create(
            chat_room=room,
            defaults={
                "student": room.student.user,
                "instructor": room.instructor.user,
                "subject": validated_data["subject"],
                "start_date": validated_data["start_date"],
            },
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
                    "verification_status": StudentPaybackAccount.VerificationStatus.UNVERIFIED,
                    "verified_at": None,
                },
            )

        registration.refresh_from_db()
        mismatched_fields = _compare_submissions(registration)
        registration.save()

        payment_to_issue = None
        if role == TutoringSubmission.Role.INSTRUCTOR:
            instructor_submission = registration.submissions.get(
                role=TutoringSubmission.Role.INSTRUCTOR
            )
            rate_bps = COMMISSION_RATES[instructor_submission.class_type]
            commission_amount = instructor_submission.first_month_fee * rate_bps // 10000
            invoice, invoice_created = CommissionInvoice.objects.get_or_create(
                registration=registration,
                invoice_type=CommissionInvoice.InvoiceType.INITIAL,
                defaults={
                    "base_amount": instructor_submission.first_month_fee,
                    "commission_rate_bps": rate_bps,
                    "commission_amount": commission_amount,
                },
            )
            if invoice_created:
                payment_to_issue = VirtualAccountPayment.objects.create(
                    invoice=invoice,
                    order_id=f"classy-{invoice.pk}-{uuid.uuid4().hex[:24]}",
                    expected_amount=commission_amount,
                )

        return {
            "registration": registration,
            "role": role,
            "mismatched_fields": mismatched_fields,
            "payment_to_issue": payment_to_issue,
        }


def create_reissue_payment(invoice):
    return VirtualAccountPayment.objects.create(
        invoice=invoice,
        order_id=f"classy-{invoice.pk}-{uuid.uuid4().hex[:24]}",
        expected_amount=invoice.commission_amount,
    )


def issue_virtual_account(payment, customer_name):
    secret_key = getattr(settings, "TOSS_PAYMENTS_SECRET_KEY", "")
    if not secret_key:
        raise VirtualAccountIssueError("TOSS_PAYMENTS_SECRET_KEY가 설정되지 않았습니다.")

    payload = {
        "amount": payment.expected_amount,
        "orderId": payment.order_id,
        "orderName": "Classy 과외 성사 수수료",
        "customerName": customer_name[:100],
        "bank": getattr(settings, "TOSS_VIRTUAL_ACCOUNT_BANK", "20"),
        "validHours": getattr(settings, "TOSS_VIRTUAL_ACCOUNT_VALID_HOURS", 168),
    }
    try:
        response = requests.post(
            "https://api.tosspayments.com/v1/virtual-accounts",
            json=payload,
            auth=(secret_key, ""),
            headers={"Idempotency-Key": payment.order_id},
            timeout=15,
        )
        response_data = response.json()
        if not response.ok:
            raise VirtualAccountIssueError(
                response_data.get("message", "가상계좌 발급에 실패했습니다."),
                response_data,
            )
    except requests.RequestException as exc:
        raise VirtualAccountIssueError("토스페이먼츠 연결에 실패했습니다.") from exc
    except ValueError as exc:
        raise VirtualAccountIssueError("토스페이먼츠 응답을 해석할 수 없습니다.") from exc

    virtual_account = response_data.get("virtualAccount") or {}
    due_at = parse_datetime(virtual_account.get("dueDate", ""))
    if due_at and timezone.is_naive(due_at):
        due_at = timezone.make_aware(due_at, timezone.get_current_timezone())

    payment.payment_key = response_data.get("paymentKey")
    payment.bank_code = virtual_account.get("bankCode", "")
    payment.account_number = virtual_account.get("accountNumber", "")
    payment.account_holder = virtual_account.get("customerName", customer_name)
    payment.toss_secret = response_data.get("secret")
    payment.due_at = due_at
    payment.fee_payment_status = VirtualAccountPayment.FeePaymentStatus.WAITING_FOR_DEPOSIT
    payment.toss_response = response_data
    payment.save()
    payment.invoice.status = CommissionInvoice.Status.PAYMENT_PENDING
    payment.invoice.save(update_fields=["status", "updated_at"])
    return payment


def mark_issue_failed(payment, error):
    payment.fee_payment_status = VirtualAccountPayment.FeePaymentStatus.FAILED
    payment.toss_response = error.payload
    payment.save(update_fields=["fee_payment_status", "toss_response", "updated_at"])
    payment.invoice.status = CommissionInvoice.Status.FAILED
    payment.invoice.save(update_fields=["status", "updated_at"])


def refresh_expiration(payment):
    if (
        payment
        and payment.fee_payment_status
        == VirtualAccountPayment.FeePaymentStatus.WAITING_FOR_DEPOSIT
        and payment.due_at
        and payment.due_at <= timezone.now()
    ):
        payment.fee_payment_status = VirtualAccountPayment.FeePaymentStatus.EXPIRED
        payment.save(update_fields=["fee_payment_status", "updated_at"])
        payment.invoice.status = CommissionInvoice.Status.FAILED
        payment.invoice.save(update_fields=["status", "updated_at"])
    return payment


def webhook_secret_matches(payment, supplied_secret):
    return bool(
        payment.toss_secret
        and supplied_secret
        and hmac.compare_digest(payment.toss_secret, supplied_secret)
    )


def serialize_payment(payment, due_key="dueAt"):
    if payment is None:
        return None
    refresh_expiration(payment)
    data = {
        "paymentId": payment.pk,
        "amount": payment.expected_amount,
        "status": payment.fee_payment_status,
        "bank": BANK_NAMES.get(payment.bank_code, payment.bank_code),
        "bankCode": payment.bank_code,
        "accountNumber": payment.account_number,
        "paidAt": payment.invoice.paid_at,
    }
    data[due_key] = payment.due_at
    return data


def latest_initial_payment(registration):
    invoice = registration.commission_invoices.filter(
        invoice_type=CommissionInvoice.InvoiceType.INITIAL
    ).first()
    if not invoice:
        return None
    return invoice.virtual_account_payments.order_by("-created_at", "-pk").first()


def latest_commission_payment(registration):
    invoice = registration.commission_invoices.order_by("-created_at", "-pk").first()
    if not invoice:
        return None
    return invoice.virtual_account_payments.order_by("-created_at", "-pk").first()


def serialize_registration(registration, user, role=None, mismatched_fields=None):
    if role is None:
        role = (
            TutoringSubmission.Role.STUDENT
            if registration.student_id == user.id
            else TutoringSubmission.Role.INSTRUCTOR
        )
    submissions = {submission.role: submission for submission in registration.submissions.all()}
    mine = submissions.get(role)
    counterparty_role = (
        TutoringSubmission.Role.INSTRUCTOR
        if role == TutoringSubmission.Role.STUDENT
        else TutoringSubmission.Role.STUDENT
    )
    counterparty = submissions.get(counterparty_role)
    if mismatched_fields is None:
        _, _, mismatched_fields = _submission_comparison(registration)

    data = {
        "registrationId": registration.pk,
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
    if registration.attribute_validation_status == TutoringRegistration.AttributeValidationStatus.MISMATCHED:
        data["mismatchedFields"] = mismatched_fields
    return data

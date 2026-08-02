"""성사등록(과외 성사) 관리 직렬화기입니다.

정산(settlement)·학력인증 직렬화기와 동일한 패턴을 따릅니다. 목록은 최소 정보 +
상태/수수료 요약을, 상세는 당사자 연락처·양측 제출 비교·수수료 인보이스·증빙·학생
페이백 계좌(전체)·처리 이력을 포함합니다. 계좌/연락처는 실제 송금·연락을 위해
마스킹하지 않으며, 접근은 뷰의 ``IsSuperAdmin`` 으로 제한됩니다.
"""

import os

from django.conf import settings
from rest_framework import serializers

from config.apps.accounts.models import Instructor
from config.apps.adminops.models import AdminActionLog
from config.apps.pending.models import PendingInstructor
from config.apps.tutoring.models import (
    CommissionInvoice,
    StudentPaybackAccount,
    TutoringRegistration,
    TutoringResource,
)
from config.apps.tutoring.registration_services import (
    _submission_comparison,
    decrypt_account_number,
)

from .instructor_verification import _real_name


def _resource(obj: TutoringRegistration):
    try:
        return obj.resource
    except TutoringResource.DoesNotExist:
        return None


def _payback_account(obj: TutoringRegistration):
    try:
        return obj.student_payback_account
    except StudentPaybackAccount.DoesNotExist:
        return None


def _initial_invoice(obj: TutoringRegistration):
    """prefetch 된 commission_invoices 캐시에서 INITIAL 인보이스를 찾는다(N+1 회피)."""
    for invoice in obj.commission_invoices.all():
        if invoice.invoice_type == CommissionInvoice.InvoiceType.INITIAL:
            return invoice
    return None


def _verification_status(user):
    """강사 User 의 학력인증 상태(PENDING/VERIFIED/SUSPENDED) 또는 None."""
    try:
        profile = user.instructor_profile
    except Instructor.DoesNotExist:
        return None
    try:
        return profile.pending_info.status
    except PendingInstructor.DoesNotExist:
        return None


class TutoringRegistrationListSerializer(serializers.ModelSerializer):
    """성사등록 목록 항목입니다."""

    student_name = serializers.SerializerMethodField()
    student_user_name = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()
    instructor_user_name = serializers.SerializerMethodField()
    fee_payment_status = serializers.SerializerMethodField()
    commission_amount = serializers.SerializerMethodField()

    class Meta:
        model = TutoringRegistration
        fields = [
            "id",
            "subject",
            "start_date",
            "attribute_validation_status",
            "contract_status",
            "fee_payment_status",
            "commission_amount",
            "student_name",
            "student_user_name",
            "instructor_name",
            "instructor_user_name",
            "created_at",
            "updated_at",
        ]

    def get_student_name(self, obj: TutoringRegistration) -> str:
        return _real_name(obj.student)

    def get_student_user_name(self, obj: TutoringRegistration) -> str:
        return obj.student.user_name

    def get_instructor_name(self, obj: TutoringRegistration) -> str:
        return _real_name(obj.instructor)

    def get_instructor_user_name(self, obj: TutoringRegistration) -> str:
        return obj.instructor.user_name

    def get_fee_payment_status(self, obj: TutoringRegistration):
        resource = _resource(obj)
        return resource.fee_payment_status if resource else None

    def get_commission_amount(self, obj: TutoringRegistration):
        invoice = _initial_invoice(obj)
        return invoice.commission_amount if invoice else None


class TutoringRegistrationDetailSerializer(TutoringRegistrationListSerializer):
    """상세 화면용. 당사자 연락처·제출 비교·인보이스·증빙·페이백 계좌를 포함합니다."""

    student = serializers.SerializerMethodField()
    instructor = serializers.SerializerMethodField()
    submissions = serializers.SerializerMethodField()
    mismatched_fields = serializers.SerializerMethodField()
    commission_invoice = serializers.SerializerMethodField()
    platform_account = serializers.SerializerMethodField()
    resource = serializers.SerializerMethodField()
    payback_account = serializers.SerializerMethodField()
    action_logs = serializers.SerializerMethodField()

    class Meta(TutoringRegistrationListSerializer.Meta):
        fields = TutoringRegistrationListSerializer.Meta.fields + [
            "confirmed_class_type",
            "confirmed_first_month_fee",
            "terms_confirmed_at",
            "chat_room_id",
            "student",
            "instructor",
            "submissions",
            "mismatched_fields",
            "commission_invoice",
            "platform_account",
            "resource",
            "payback_account",
            "action_logs",
        ]

    def _party(self, user, *, include_verification=False):
        """당사자 정보. SuperAdmin 전용이라 이메일·전화 전체 노출."""
        data = {
            "id": user.id,
            "real_name": _real_name(user),
            "user_name": user.user_name,
            "email": user.email,
            "phone": user.phone,
        }
        if include_verification:
            data["verification_status"] = _verification_status(user)
        return data

    def get_student(self, obj: TutoringRegistration):
        return self._party(obj.student)

    def get_instructor(self, obj: TutoringRegistration):
        return self._party(obj.instructor, include_verification=True)

    def get_submissions(self, obj: TutoringRegistration):
        return [
            {
                "role": submission.role,
                "class_type": submission.class_type,
                "first_month_fee": submission.first_month_fee,
                "submitted_by": submission.submitted_by.user_name,
                "submitted_at": submission.updated_at,
            }
            for submission in obj.submissions.all()
        ]

    def get_mismatched_fields(self, obj: TutoringRegistration):
        _, _, mismatched_fields = _submission_comparison(obj)
        return mismatched_fields

    def get_commission_invoice(self, obj: TutoringRegistration):
        invoice = _initial_invoice(obj)
        if invoice is None:
            return None
        return {
            "id": invoice.pk,
            "base_amount": invoice.base_amount,
            "commission_rate_bps": invoice.commission_rate_bps,
            "commission_amount": invoice.commission_amount,
            "status": invoice.status,
            "paid_at": invoice.paid_at,
        }

    def get_platform_account(self, obj: TutoringRegistration):
        """강사가 성사 수수료를 입금하는 플랫폼 계좌(대사 기준)."""
        return {
            "bank": settings.TUTORING_PAYMENT_BANK,
            "account_number": settings.TUTORING_PAYMENT_ACCOUNT_NUMBER,
        }

    def get_resource(self, obj: TutoringRegistration):
        resource = _resource(obj)
        if resource is None:
            return None
        return {
            "id": resource.pk,
            "fee_payment_status": resource.fee_payment_status,
            "expected_commission_amount": resource.expected_commission_amount,
            "files": [
                {
                    "id": f.pk,
                    "filename": os.path.basename(f.file.name),
                    "extension": (
                        f.file.name.rsplit(".", 1)[-1].lower()
                        if "." in f.file.name
                        else ""
                    ),
                    "uploaded_at": f.uploaded_at,
                }
                for f in resource.files.all()
            ],
        }

    def get_payback_account(self, obj: TutoringRegistration):
        """학생 페이백 계좌(전체). 실제 송금용이라 마스킹하지 않습니다."""
        account = _payback_account(obj)
        if account is None:
            return None
        try:
            account_number = decrypt_account_number(account.encrypted_account_number)
        except Exception:
            account_number = None
        return {
            "bank_code": account.bank_code,
            "account_number": account_number,
            "account_holder": account.account_holder,
            "verification_status": account.verification_status,
            "verified_at": account.verified_at,
        }

    def get_action_logs(self, obj: TutoringRegistration):
        logs = AdminActionLog.objects.filter(
            target_type="TutoringRegistration", target_id=str(obj.pk)
        ).order_by("-created_at")
        return [
            {
                "action": log.action,
                "admin_email": log.admin_email,
                "reason": log.reason,
                "created_at": log.created_at,
            }
            for log in logs
        ]


class RejectFeeSerializer(serializers.Serializer):
    """수수료 반려 입력. 사유는 선택(감사 로그 기록용)입니다."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")

"""성사등록 페이백 생성과 운영자 지급 처리 규칙입니다."""

from django.db import transaction
from django.utils import timezone

from config.apps.adminops.exceptions import ConflictError, ValidationError
from config.apps.adminops.models import AdminActionLog

from .models import PaybackPayout, TutoringRegistration

PAYBACK_RATE_BPS = 50


def calculate_payback_amount(first_month_fee: int) -> int:
    """확정 첫 달 수업료의 0.5%를 원 단위로 절사합니다."""
    return first_month_fee * PAYBACK_RATE_BPS // 10_000


def ensure_payback_payout(registration: TutoringRegistration) -> PaybackPayout | None:
    """ACTIVE 성사등록에 멱등적으로 지급 대기 레코드를 만듭니다."""
    if registration.contract_status != TutoringRegistration.ContractStatus.ACTIVE:
        return None
    if registration.confirmed_first_month_fee is None:
        return None
    payout, _ = PaybackPayout.objects.get_or_create(
        registration=registration,
        defaults={"amount": calculate_payback_amount(registration.confirmed_first_month_fee)},
    )
    return payout


def _payout_or_error(registration_id: int) -> PaybackPayout:
    try:
        return PaybackPayout.objects.select_for_update().select_related("registration__student").get(registration_id=registration_id)
    except PaybackPayout.DoesNotExist as exc:
        raise ValidationError("페이백 지급 대기 건이 없습니다.") from exc


@transaction.atomic
def complete_payback(*, registration_id: int, admin, payment_reference: str, request_id: str = "") -> PaybackPayout:
    """대기 중 페이백을 참조번호와 함께 완료하고 학생에게 알립니다."""
    payment_reference = (payment_reference or "").strip()
    if not payment_reference:
        raise ValidationError("지급 참조번호를 입력해야 합니다.")
    payout = _payout_or_error(registration_id)
    if payout.status != PaybackPayout.Status.PENDING:
        raise ConflictError("지급 대기 상태에서만 완료 처리할 수 있습니다.")
    payout.status = PaybackPayout.Status.COMPLETED
    payout.payment_reference = payment_reference
    payout.failure_reason = ""
    payout.processed_at = timezone.now()
    payout.save(update_fields=["status", "payment_reference", "failure_reason", "processed_at", "updated_at"])
    AdminActionLog.record(admin=admin, action="payback.complete", target_type="PaybackPayout", target_id=payout.pk, metadata={"registration_id": registration_id, "amount": payout.amount, "payment_reference": payment_reference}, request_id=request_id)
    from config.apps.notification.helpers import notify_payback_completed
    notify_payback_completed(payout.registration.student, registration_id=registration_id, amount=payout.amount)
    return payout


@transaction.atomic
def fail_payback(*, registration_id: int, admin, reason: str, request_id: str = "") -> PaybackPayout:
    """대기 중 페이백의 실패 사유를 기록합니다."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("실패 사유를 입력해야 합니다.")
    payout = _payout_or_error(registration_id)
    if payout.status != PaybackPayout.Status.PENDING:
        raise ConflictError("지급 대기 상태에서만 실패 처리할 수 있습니다.")
    payout.status = PaybackPayout.Status.FAILED
    payout.failure_reason = reason
    payout.processed_at = timezone.now()
    payout.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
    AdminActionLog.record(admin=admin, action="payback.fail", target_type="PaybackPayout", target_id=payout.pk, reason=reason, metadata={"registration_id": registration_id}, request_id=request_id)
    return payout


@transaction.atomic
def retry_payback(*, registration_id: int, admin, request_id: str = "") -> PaybackPayout:
    """실패한 지급을 다시 지급 대기 상태로 되돌립니다."""
    payout = _payout_or_error(registration_id)
    if payout.status != PaybackPayout.Status.FAILED:
        raise ConflictError("지급 실패 건만 재처리할 수 있습니다.")
    payout.status = PaybackPayout.Status.PENDING
    payout.failure_reason = ""
    payout.processed_at = None
    payout.payment_reference = ""
    payout.save(update_fields=["status", "failure_reason", "processed_at", "payment_reference", "updated_at"])
    AdminActionLog.record(admin=admin, action="payback.retry", target_type="PaybackPayout", target_id=payout.pk, metadata={"registration_id": registration_id}, request_id=request_id)
    return payout

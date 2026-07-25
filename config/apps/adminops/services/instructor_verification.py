"""학력 인증 승인/반려 공유 서비스입니다.

관리자 API 뷰와 Django Admin 액션이 **동일한 이 함수**를 호출해 상태 전이를
수행합니다. 모든 전이는 트랜잭션 안에서 `select_for_update()` 로 레코드를 잠가
동시 처리를 방지하고, 처리자·시각을 남기며 `AdminActionLog` 에 감사 기록을 씁니다.
"""

from django.db import transaction
from django.utils import timezone

from config.apps.adminops.exceptions import ConflictError, ValidationError
from config.apps.adminops.models import AdminActionLog
from config.apps.pending.models import PendingInstructor

TARGET_TYPE = "PendingInstructor"


def _lock(pending_id: int) -> PendingInstructor:
    return PendingInstructor.objects.select_for_update().get(pk=pending_id)


@transaction.atomic
def approve(pending: PendingInstructor, *, admin, request_id: str = "") -> PendingInstructor:
    """학력 인증을 승인합니다(PENDING → VERIFIED).

    Raises:
        ConflictError: 대상이 PENDING 상태가 아닌 경우.
    """
    pending = _lock(pending.pk)
    if pending.status != PendingInstructor.Status.PENDING:
        raise ConflictError("인증 대기(PENDING) 상태에서만 승인할 수 있습니다.")

    before = pending.status
    pending.status = PendingInstructor.Status.VERIFIED
    pending.reviewed_by = admin
    pending.reviewed_at = timezone.now()
    pending.rejection_reason = ""
    pending.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"]
    )

    AdminActionLog.record(
        admin=admin,
        action="instructor_verification.approve",
        target_type=TARGET_TYPE,
        target_id=pending.pk,
        metadata={"before": before, "after": pending.status},
        request_id=request_id,
    )
    return pending


@transaction.atomic
def reject(
    pending: PendingInstructor, *, admin, reason: str, request_id: str = ""
) -> PendingInstructor:
    """학력 인증을 반려합니다(PENDING → SUSPENDED). 사유 입력 필수.

    Raises:
        ValidationError: 사유가 비어 있는 경우.
        ConflictError: 대상이 PENDING 상태가 아닌 경우.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("반려 사유를 입력해야 합니다.")

    pending = _lock(pending.pk)
    if pending.status != PendingInstructor.Status.PENDING:
        raise ConflictError("인증 대기(PENDING) 상태에서만 반려할 수 있습니다.")

    before = pending.status
    pending.status = PendingInstructor.Status.SUSPENDED
    pending.rejection_reason = reason
    pending.reviewed_by = admin
    pending.reviewed_at = timezone.now()
    pending.save(
        update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"]
    )

    AdminActionLog.record(
        admin=admin,
        action="instructor_verification.reject",
        target_type=TARGET_TYPE,
        target_id=pending.pk,
        reason=reason,
        metadata={"before": before, "after": pending.status},
        request_id=request_id,
    )
    return pending

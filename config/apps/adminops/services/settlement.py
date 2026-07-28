"""정산 완료/취소 공유 서비스입니다.

관리자 API 뷰와 Django Admin 액션이 **동일한 이 함수**를 호출해 상태 전이를
수행할 수 있도록 설계했습니다. 모든 전이는 트랜잭션 안에서 ``select_for_update()``
로 레코드를 잠가 동시 처리를 방지하고, 처리 시각을 남기며 ``AdminActionLog`` 에
감사 기록을 씁니다. 실제 KRW 송금/계좌 처리는 자동화하지 않습니다.
"""

from django.db import transaction
from django.utils import timezone

from config.apps.adminops.exceptions import ConflictError, ValidationError
from config.apps.adminops.models import AdminActionLog
from config.apps.cash.models import SettlementRecord

TARGET_TYPE = "SettlementRecord"


def _lock(settlement_id: int) -> SettlementRecord:
    return SettlementRecord.objects.select_for_update().get(pk=settlement_id)


@transaction.atomic
def complete(
    settlement: SettlementRecord,
    *,
    admin,
    payment_reference: str,
    admin_note: str = "",
    request_id: str = "",
) -> SettlementRecord:
    """정산을 완료 처리합니다(PENDING → COMPLETED). 지급 참조번호 필수.

    Raises:
        ValidationError: 지급 참조번호가 비어 있는 경우.
        ConflictError: 대상이 PENDING 상태가 아닌 경우.
    """
    payment_reference = (payment_reference or "").strip()
    if not payment_reference:
        raise ValidationError("지급 참조번호를 입력해야 합니다.")

    settlement = _lock(settlement.pk)
    if settlement.status != "PENDING":
        raise ConflictError("대기(PENDING) 상태에서만 완료할 수 있습니다.")

    before = settlement.status
    settlement.status = "COMPLETED"
    settlement.processed_at = timezone.now()
    settlement.payment_reference = payment_reference
    settlement.admin_note = admin_note or ""
    settlement.save(
        update_fields=["status", "processed_at", "payment_reference", "admin_note"]
    )

    AdminActionLog.record(
        admin=admin,
        action="settlement.complete",
        target_type=TARGET_TYPE,
        target_id=settlement.pk,
        metadata={
            "before": before,
            "after": settlement.status,
            "payment_reference": payment_reference,
        },
        request_id=request_id,
    )
    return settlement


@transaction.atomic
def cancel(
    settlement: SettlementRecord,
    *,
    admin,
    reason: str = "",
    request_id: str = "",
) -> SettlementRecord:
    """정산을 취소 처리합니다(PENDING·COMPLETED → CANCELED).

    연결된 대여를 ``is_settled=False, settlement=None`` 으로 롤백해 강사가 다시
    정산을 신청할 수 있게 합니다.

    Raises:
        ConflictError: 대상이 이미 CANCELED 인 경우.
    """
    settlement = _lock(settlement.pk)
    if settlement.status == "CANCELED":
        raise ConflictError("이미 취소된 정산입니다.")

    before = settlement.status
    settlement.status = "CANCELED"
    settlement.processed_at = timezone.now()
    settlement.save(update_fields=["status", "processed_at"])

    # 연결된 대여를 미정산 상태로 롤백해 강사 재신청을 허용한다.
    settlement.rentals.all().update(is_settled=False, settlement=None)

    AdminActionLog.record(
        admin=admin,
        action="settlement.cancel",
        target_type=TARGET_TYPE,
        target_id=settlement.pk,
        reason=reason or "",
        metadata={"before": before, "after": settlement.status},
        request_id=request_id,
    )
    return settlement

"""성사등록 수수료 확인/반려 공유 서비스입니다.

상태 전이 자체는 tutoring 도메인 서비스(``registration_services.confirm_fee_payment`` /
``mark_fee_payment_failed``)에 위임하고, 이 adminops 계층은 트랜잭션·행 잠금
(``select_for_update``)·상태 가드·``AdminActionLog`` 감사 기록을 담당한다. 정산
서비스(``services/settlement.py``)와 동일한 패턴이다.
"""

from django.db import transaction

from config.apps.adminops.exceptions import ConflictError, ValidationError
from config.apps.adminops.models import AdminActionLog
from config.apps.tutoring.models import TutoringResource
from config.apps.tutoring.registration_services import (
    confirm_fee_payment as _confirm_fee_payment,
    mark_fee_payment_failed as _mark_fee_payment_failed,
)

TARGET_TYPE = "TutoringRegistration"


def _lock_resource(registration) -> TutoringResource:
    """등록에 연결된 리소스를 잠가 반환한다. 없으면 ValidationError."""
    resource = (
        TutoringResource.objects.select_for_update()
        .filter(registration=registration)
        .first()
    )
    if resource is None:
        raise ValidationError("연결된 과외 리소스가 없어 수수료를 처리할 수 없습니다.")
    return resource


@transaction.atomic
def confirm_fee(registration, *, admin, request_id: str = ""):
    """수수료 입금을 확인 처리한다(AWAITING_CONFIRMATION → PAID).

    Raises:
        ValidationError: 연결된 리소스가 없는 경우.
        ConflictError: 확인 대기 상태가 아닌 경우.
    """
    resource = _lock_resource(registration)
    if resource.fee_payment_status != "AWAITING_CONFIRMATION":
        raise ConflictError(
            "확인 대기(AWAITING_CONFIRMATION) 상태에서만 확인할 수 있습니다."
        )

    before = resource.fee_payment_status
    _confirm_fee_payment(resource)

    AdminActionLog.record(
        admin=admin,
        action="tutoring_registration.confirm_fee",
        target_type=TARGET_TYPE,
        target_id=registration.pk,
        metadata={
            "before": before,
            "after": resource.fee_payment_status,
            "resource_id": resource.pk,
        },
        request_id=request_id,
    )
    return registration


@transaction.atomic
def reject_fee(registration, *, admin, reason: str = "", request_id: str = ""):
    """수수료 입금을 반려 처리한다(PENDING·AWAITING_CONFIRMATION → FAILED).

    Raises:
        ValidationError: 연결된 리소스가 없는 경우.
        ConflictError: 입금 전·확인 대기 상태가 아닌 경우.
    """
    resource = _lock_resource(registration)
    if resource.fee_payment_status not in ("PENDING", "AWAITING_CONFIRMATION"):
        raise ConflictError(
            "입금 전(PENDING)·확인 대기(AWAITING_CONFIRMATION) 상태에서만 반려할 수 있습니다."
        )

    before = resource.fee_payment_status
    _mark_fee_payment_failed(resource, notify=True)

    AdminActionLog.record(
        admin=admin,
        action="tutoring_registration.reject_fee",
        target_type=TARGET_TYPE,
        target_id=registration.pk,
        reason=reason or "",
        metadata={
            "before": before,
            "after": resource.fee_payment_status,
            "resource_id": resource.pk,
        },
        request_id=request_id,
    )
    return registration

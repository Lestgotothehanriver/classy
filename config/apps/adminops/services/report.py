"""신고 처리 공유 서비스입니다.

정산(``services/settlement.py``)·성사(``services/tutoring_registration.py``) 서비스와
동일하게 트랜잭션 + ``select_for_update`` + 상태 가드 + ``AdminActionLog`` 감사 기록을
담당한다. 신고 처리는 순수 관리자 개념이라 별도 도메인 서비스에 위임하지 않고 여기서
상태를 전이한다.

결정은 **가해자(reported_user) 단위**로 이뤄진다(통합 케이스). ``resolve_case`` 는 그
유저의 미처리 신고를 일괄 종결하고, 필요 시 단계별 제재(``UserSanction``)를 함께
발급한다. 콘텐츠 조치(영상 내리기/댓글 삭제)는 Phase 2에서 추가된다.
"""

from django.db import transaction
from django.utils import timezone

from config.apps.accounts.models import UserSanction, recompute_ban_state
from config.apps.adminops.exceptions import ConflictError, ValidationError
from config.apps.adminops.models import AdminActionLog
from config.apps.report.models import Report, ReportStatusChoices

TARGET_TYPE = "Report"
USER_TARGET_TYPE = "User"

_OPEN_STATUSES = (ReportStatusChoices.PENDING, ReportStatusChoices.IN_REVIEW)
_OUTCOMES = {ReportStatusChoices.RESOLVED, ReportStatusChoices.DISMISSED}

# 콘텐츠 조치 대상: content_type 문자열 → (모듈, 모델명).
_CONTENT_MODEL_PATHS = {
    "lecture": ("config.apps.lecture.models", "Lecture"),
    "comment": ("config.apps.lecture.models", "Comment"),
    "tutoring_post": ("config.apps.tutoring.models", "TutoringPost"),
}


def resolve_content(content_type: str, object_id):
    """(content_type, object_id) 를 실제 콘텐츠 인스턴스로 해석한다.

    Raises:
        ValidationError: 알 수 없는 유형이거나 대상이 없는 경우.
    """
    import importlib

    entry = _CONTENT_MODEL_PATHS.get(content_type)
    if not entry:
        raise ValidationError("차단할 수 없는 콘텐츠 유형입니다.")
    module_path, model_name = entry
    model = getattr(importlib.import_module(module_path), model_name)
    try:
        return model.objects.get(pk=object_id)
    except model.DoesNotExist:
        raise ValidationError("콘텐츠를 찾을 수 없습니다.")


def _apply_block(obj, admin, *, block: bool):
    """콘텐츠 유형별 잠금 필드를 세팅한다(영상·공고=admin_blocked, 댓글=is_blocked)."""
    from config.apps.lecture.models import Comment, Lecture
    from config.apps.tutoring.models import TutoringPost

    now = timezone.now() if block else None
    if isinstance(obj, Comment):
        obj.is_blocked = block
        obj.blocked_at = now
        obj.blocked_by = admin if block else None
        obj.save(update_fields=["is_blocked", "blocked_at", "blocked_by"])
    elif isinstance(obj, (Lecture, TutoringPost)):
        obj.admin_blocked_at = now
        obj.admin_blocked_by = admin if block else None
        obj.save(update_fields=["admin_blocked_at", "admin_blocked_by"])
    else:
        raise ValidationError("차단할 수 없는 콘텐츠 유형입니다.")


@transaction.atomic
def block_content(obj, *, admin, request_id: str = ""):
    """콘텐츠를 차단한다(영상·공고 노출/재생 차단, 댓글 tombstone 마스킹)."""
    _apply_block(obj, admin, block=True)
    AdminActionLog.record(
        admin=admin,
        action="report.block_content",
        target_type=type(obj).__name__,
        target_id=obj.pk,
        request_id=request_id,
    )
    return obj


@transaction.atomic
def unblock_content(obj, *, admin, request_id: str = ""):
    """콘텐츠 차단을 해제한다."""
    _apply_block(obj, admin, block=False)
    AdminActionLog.record(
        admin=admin,
        action="report.unblock_content",
        target_type=type(obj).__name__,
        target_id=obj.pk,
        request_id=request_id,
    )
    return obj


@transaction.atomic
def set_in_review(report, *, admin, request_id: str = ""):
    """신고를 보류(검토중)로 전환한다(PENDING → IN_REVIEW).

    Raises:
        ConflictError: 미처리(PENDING) 상태가 아닌 경우.
    """
    report = Report.objects.select_for_update().get(pk=report.pk)
    if report.status != ReportStatusChoices.PENDING:
        raise ConflictError("미처리(PENDING) 상태에서만 보류로 전환할 수 있습니다.")

    before = report.status
    report.status = ReportStatusChoices.IN_REVIEW
    report.save(update_fields=["status"])

    AdminActionLog.record(
        admin=admin,
        action="report.in_review",
        target_type=TARGET_TYPE,
        target_id=report.pk,
        metadata={"before": before, "after": report.status},
        request_id=request_id,
    )
    return report


@transaction.atomic
def issue_sanction(
    user,
    *,
    admin,
    sanction_type: str,
    reason: str = "",
    expires_at=None,
    report=None,
    request_id: str = "",
):
    """제재를 발급하고 ``is_banned`` 를 재계산한다.

    Raises:
        ValidationError: 알 수 없는 제재 유형인 경우.
    """
    if sanction_type not in set(UserSanction.Type.values):
        raise ValidationError("알 수 없는 제재 유형입니다.")

    sanction = UserSanction.objects.create(
        target_user=user,
        type=sanction_type,
        reason=reason or "",
        expires_at=expires_at,
        report=report,
        issued_by=admin,
    )
    recompute_ban_state(user)

    AdminActionLog.record(
        admin=admin,
        action="report.sanction",
        target_type=USER_TARGET_TYPE,
        target_id=user.pk,
        reason=reason or "",
        metadata={
            "sanction_id": sanction.pk,
            "type": sanction_type,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "report_id": report.pk if report is not None else None,
        },
        request_id=request_id,
    )
    return sanction


@transaction.atomic
def lift_sanction(sanction, *, admin, reason: str = "", request_id: str = ""):
    """제재를 해제하고 ``is_banned`` 를 재계산한다.

    Raises:
        ConflictError: 이미 해제된 제재인 경우.
    """
    sanction = UserSanction.objects.select_for_update().get(pk=sanction.pk)
    if not sanction.is_active:
        raise ConflictError("이미 해제된 제재입니다.")

    sanction.is_active = False
    sanction.save(update_fields=["is_active"])
    recompute_ban_state(sanction.target_user)

    AdminActionLog.record(
        admin=admin,
        action="report.lift_sanction",
        target_type=USER_TARGET_TYPE,
        target_id=sanction.target_user_id,
        reason=reason or "",
        metadata={"sanction_id": sanction.pk},
        request_id=request_id,
    )
    return sanction


@transaction.atomic
def resolve_case(
    reported_user,
    *,
    admin,
    outcome: str,
    reason: str = "",
    sanction: dict | None = None,
    content_actions: list | None = None,
    request_id: str = "",
):
    """가해자의 미처리 신고를 일괄 종결하고, 선택적으로 콘텐츠 조치·제재를 함께 수행한다.

    Args:
        outcome: ``RESOLVED``(조치완료) 또는 ``DISMISSED``(무혐의).
        sanction: ``{"type", "reason", "expires_at"}`` 또는 ``None``.
        content_actions: ``[{"content_type", "object_id", "action"}]`` (block|unblock).

    Raises:
        ValidationError: outcome/콘텐츠 조치가 유효하지 않은 경우.
        ConflictError: 처리할 미처리 신고도 없고 제재도 없는 경우.
    """
    if outcome not in _OUTCOMES:
        raise ValidationError("처리 결과는 조치완료/무혐의 중 하나여야 합니다.")

    open_reports = list(
        Report.objects.select_for_update().filter(
            reported_user=reported_user, status__in=_OPEN_STATUSES
        )
    )
    if not open_reports and not sanction and not content_actions:
        raise ConflictError("처리할 미처리 신고가 없습니다.")

    # 콘텐츠 조치(영상 내리기/댓글 삭제 등)를 먼저 적용한다.
    for action in content_actions or []:
        obj = resolve_content(action.get("content_type"), action.get("object_id"))
        if action.get("action") == "unblock":
            unblock_content(obj, admin=admin, request_id=request_id)
        else:
            block_content(obj, admin=admin, request_id=request_id)

    issued = None
    if sanction:
        issued = issue_sanction(
            reported_user,
            admin=admin,
            sanction_type=sanction.get("type"),
            reason=sanction.get("reason") or reason,
            expires_at=sanction.get("expires_at"),
            report=open_reports[0] if open_reports else None,
            request_id=request_id,
        )

    report_ids = [r.pk for r in open_reports]
    if report_ids:
        Report.objects.filter(pk__in=report_ids).update(
            status=outcome,
            resolved_at=timezone.now(),
            resolved_by=admin,
            resolution_note=reason or "",
        )
        action = (
            "report.resolve"
            if outcome == ReportStatusChoices.RESOLVED
            else "report.dismiss"
        )
        AdminActionLog.record(
            admin=admin,
            action=action,
            target_type=USER_TARGET_TYPE,
            target_id=reported_user.pk,
            reason=reason or "",
            metadata={
                "report_ids": report_ids,
                "outcome": outcome,
                "sanction_id": issued.pk if issued else None,
            },
            request_id=request_id,
        )

    return {
        "reported_user": reported_user,
        "resolved_report_ids": report_ids,
        "sanction": issued,
    }

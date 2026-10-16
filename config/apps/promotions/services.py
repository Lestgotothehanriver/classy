"""프로모션 자격 판정과 혜택 사용을 한곳에서 관리합니다."""

from calendar import monthrange
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .models import InstructorPromotionBenefit, PromotionCampaign

KST = ZoneInfo("Asia/Seoul")


def _add_calendar_months(value: datetime, months: int) -> datetime:
    """[value]에 달력 기준 [months]개월을 더한 KST 시각을 반환합니다."""
    localized = value.astimezone(KST)
    month_index = localized.month - 1 + months
    year = localized.year + month_index // 12
    month = month_index % 12 + 1
    day = min(localized.day, monthrange(year, month)[1])
    return localized.replace(year=year, month=month, day=day)


def assign_signup_promotion(instructor, *, now: datetime | None = None):
    """신규 강사 [instructor]에게 현재 가입 가능한 캠페인 혜택을 확정합니다."""
    applied_at = now or timezone.now()
    campaign = (
        PromotionCampaign.objects.filter(
            is_active=True,
            signup_starts_at__lte=applied_at,
            signup_ends_at__gt=applied_at,
        )
        .order_by("-signup_starts_at", "-id")
        .first()
    )
    if campaign is None:
        return None
    return InstructorPromotionBenefit.objects.create(
        campaign=campaign,
        instructor=instructor,
        benefit_starts_at=applied_at,
        benefit_ends_at=_add_calendar_months(applied_at, campaign.benefit_months),
        tutoring_registration_limit=campaign.tutoring_registration_limit,
        tutoring_commission_rate_bps=campaign.tutoring_commission_rate_bps,
        lecture_settlement_fee_rate_bps=campaign.lecture_settlement_fee_rate_bps,
    )


def active_benefit_for(instructor, *, now: datetime | None = None):
    """[instructor]의 유효한 혜택을 종료 시각 기준으로 반환합니다."""
    current = now or timezone.now()
    return (
        InstructorPromotionBenefit.objects.filter(
            instructor=instructor,
            benefit_starts_at__lte=current,
            benefit_ends_at__gt=current,
        )
        .select_related("campaign")
        .order_by("benefit_ends_at", "id")
        .first()
    )


def promotion_summary_for(instructor, *, now: datetime | None = None):
    """강사 홈에 표시할 현재 혜택 요약을 반환합니다."""
    benefit = active_benefit_for(instructor, now=now)
    if benefit is None:
        return None
    return {
        "ends_at": benefit.benefit_ends_at,
        "remaining_tutoring_registration_count": max(
            benefit.tutoring_registration_limit
            - benefit.used_tutoring_registration_count,
            0,
        ),
        "tutoring_registration_limit": benefit.tutoring_registration_limit,
        "tutoring_commission_rate_bps": benefit.tutoring_commission_rate_bps,
        "lecture_settlement_fee_rate_bps": benefit.lecture_settlement_fee_rate_bps,
    }


def annotate_featured_instructors(queryset, *, now: datetime | None = None):
    """현재 검색 결과의 혜택 강사 여부를 정렬용 플래그로 주석 처리합니다."""
    current = now or timezone.now()
    benefits = InstructorPromotionBenefit.objects.filter(
        instructor_id=OuterRef("pk"),
        benefit_starts_at__lte=current,
        benefit_ends_at__gt=current,
    )
    return queryset.annotate(is_promotion_featured=Exists(benefits))


@transaction.atomic
def reserve_tutoring_benefit(instructor, *, now: datetime | None = None):
    """과외 성사 수수료에 적용할 혜택을 예약하되 사용 건수는 늘리지 않습니다."""
    from config.apps.tutoring.models import CommissionInvoice

    current = now or timezone.now()
    benefits = (
        InstructorPromotionBenefit.objects.select_for_update()
        .filter(
            instructor=instructor,
            benefit_starts_at__lte=current,
            benefit_ends_at__gt=current,
        )
        .select_related("campaign")
        .order_by("benefit_ends_at", "id")
    )
    for benefit in benefits:
        pending_reservation_count = CommissionInvoice.objects.filter(
            promotion_benefit=benefit,
            invoice_type=CommissionInvoice.InvoiceType.INITIAL,
            status__in=[
                CommissionInvoice.Status.READY,
                CommissionInvoice.Status.PAYMENT_PENDING,
            ],
        ).count()
        if (
            benefit.used_tutoring_registration_count + pending_reservation_count
            < benefit.tutoring_registration_limit
        ):
            return benefit, None
    return None, None


@transaction.atomic
def consume_confirmed_tutoring_benefit(invoice):
    """입금 확인 완료된 [invoice]의 프로모션 사용 건수를 한 번만 증가시킵니다."""
    if invoice.promotion_benefit_id is None or invoice.promotion_usage_number is not None:
        return

    benefit = (
        InstructorPromotionBenefit.objects.select_for_update()
        .filter(pk=invoice.promotion_benefit_id)
        .first()
    )
    if (
        benefit is None
        or benefit.used_tutoring_registration_count
        >= benefit.tutoring_registration_limit
    ):
        return

    benefit.used_tutoring_registration_count += 1
    benefit.save(update_fields=["used_tutoring_registration_count"])
    invoice.promotion_usage_number = benefit.used_tutoring_registration_count
    invoice.save(update_fields=["promotion_usage_number", "updated_at"])

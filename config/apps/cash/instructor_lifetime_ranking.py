"""강사의 무기한 누적 랭킹을 원장에서 계산하는 조회 서비스입니다.

월간 스냅샷을 읽지 않고, 조회 시점에 유효한 과외 수수료와 강의 판매
캐시를 합산합니다. 이 모듈은 화면 필터와 독립적인 전역 순위를 한 번
계산한 뒤, 호출자가 필요한 강사 ID의 순위만 읽도록 제공합니다.
"""

from dataclasses import dataclass

from django.db.models import BigIntegerField, Exists, F, OuterRef, Q, Subquery, Sum, Value, Window
from django.db.models.functions import Coalesce, Rank
from django.utils import timezone

from config.apps.accounts.models import Instructor, UserSanction
from config.apps.cash.models import LectureRentalHistory
from config.apps.tutoring.models import CommissionInvoice, TutoringRegistration


@dataclass(frozen=True)
class InstructorLifetimeRank:
    """한 강사의 누적 점수와 전역 공동 순위를 보관합니다."""

    rank: int
    score: int


def _eligible_instructors_with_score():
    """랭킹 참가 조건을 만족하는 강사에 유효 원장 합계를 annotate합니다."""

    now = timezone.now()
    effective_sanctions = UserSanction.objects.filter(
        target_user_id=OuterRef("user_id"),
        is_active=True,
        type__in=[
            UserSanction.Type.SUSPENSION,
            UserSanction.Type.PERMANENT_BAN,
        ],
        starts_at__lte=now,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    lecture_sales = (
        LectureRentalHistory.objects.filter(
            lecture__instructor_id=OuterRef("pk"),
            is_sandbox=False,
            is_canceled=False,
        )
        .values("lecture__instructor_id")
        .annotate(total=Sum("purchased_cash"))
        .values("total")[:1]
    )
    paid_commissions = (
        CommissionInvoice.objects.filter(
            registration__instructor_id=OuterRef("user_id"),
            registration__contract_status=TutoringRegistration.ContractStatus.ACTIVE,
            status=CommissionInvoice.Status.PAID,
        )
        .values("registration__instructor_id")
        .annotate(total=Sum("commission_amount"))
        .values("total")[:1]
    )

    return (
        Instructor.objects.filter(
            user__is_active=True,
            user__deleted_at__isnull=True,
        )
        .annotate(has_effective_rank_sanction=Exists(effective_sanctions))
        .filter(has_effective_rank_sanction=False)
        .annotate(
            lifetime_rank_score=(
                Coalesce(
                    Subquery(lecture_sales, output_field=BigIntegerField()),
                    Value(0),
                    output_field=BigIntegerField(),
                )
                + Coalesce(
                    Subquery(paid_commissions, output_field=BigIntegerField()),
                    Value(0),
                    output_field=BigIntegerField(),
                )
            )
        )
        .filter(lifetime_rank_score__gt=0)
    )


def lifetime_rankings() -> dict[int, InstructorLifetimeRank]:
    """현재 원장 기준의 전역 누적 순위를 강사 ID별로 반환합니다.

    ``Rank`` 윈도우 함수는 동점 다음 순위를 건너뛰므로 1위, 1위, 3위의
    공동 순위 정책을 그대로 만족합니다. 여기서 전체 결과를 평가한 뒤
    딕셔너리로 변환해, 화면 검색·지역 필터가 순위 계산에 영향을 주지
    않도록 합니다.
    """

    ranked_instructors = _eligible_instructors_with_score().annotate(
        current_rank=Window(
            expression=Rank(),
            order_by=F("lifetime_rank_score").desc(),
        )
    )
    return {
        row["pk"]: InstructorLifetimeRank(
            rank=row["current_rank"],
            score=row["lifetime_rank_score"],
        )
        for row in ranked_instructors.values(
            "pk",
            "current_rank",
            "lifetime_rank_score",
        )
    }


def lifetime_ranked_instructor_ids() -> list[int]:
    """랭킹 대상 강사 ID를 점수 높은 순서로 반환합니다.

    동점자는 동일 순위를 가지므로, 같은 점수 안에서는 최근 생성된 강사를
    먼저 노출해 정렬 결과를 안정적으로 유지합니다.
    """

    return list(
        _eligible_instructors_with_score()
        .order_by("-lifetime_rank_score", "-pk")
        .values_list("pk", flat=True)
    )


def lifetime_rank_for(instructor_id: int) -> InstructorLifetimeRank | None:
    """[instructor_id] 강사의 현재 누적 순위를 반환하거나 미대상을 반환합니다."""

    return lifetime_rankings().get(instructor_id)

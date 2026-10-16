"""강사 출시 프로모션의 영속 모델입니다."""

from django.db import models


class PromotionCampaign(models.Model):
    """운영자가 설정하는 강사 가입 프로모션입니다."""

    name = models.CharField(max_length=120)
    signup_starts_at = models.DateTimeField()
    signup_ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    benefit_months = models.PositiveSmallIntegerField(default=3)
    tutoring_registration_limit = models.PositiveSmallIntegerField(default=3)
    tutoring_commission_rate_bps = models.PositiveIntegerField(default=50)
    lecture_settlement_fee_rate_bps = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-signup_starts_at", "-id"]

    def __str__(self) -> str:
        """관리 화면에서 사용할 캠페인 이름을 반환합니다."""
        return self.name


class InstructorPromotionBenefit(models.Model):
    """가입 시 확정되는 강사별 프로모션 혜택 스냅샷입니다."""

    campaign = models.ForeignKey(
        PromotionCampaign,
        on_delete=models.PROTECT,
        related_name="benefits",
    )
    instructor = models.ForeignKey(
        "accounts.Instructor",
        on_delete=models.PROTECT,
        related_name="promotion_benefits",
    )
    benefit_starts_at = models.DateTimeField()
    benefit_ends_at = models.DateTimeField()
    tutoring_registration_limit = models.PositiveSmallIntegerField(default=3)
    tutoring_commission_rate_bps = models.PositiveIntegerField(default=50)
    lecture_settlement_fee_rate_bps = models.PositiveIntegerField(default=0)
    used_tutoring_registration_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "instructor"],
                name="unique_campaign_instructor_benefit",
            ),
        ]
        indexes = [
            models.Index(
                fields=["instructor", "benefit_ends_at"],
                name="promotion_instructor_end_idx",
            ),
        ]

    def __str__(self) -> str:
        """감사 로그용 사람이 읽기 쉬운 식별자를 반환합니다."""
        return f"{self.campaign.name} - {self.instructor_id}"

"""Django Admin 보조 관리 화면입니다."""

from django.contrib import admin

from .models import InstructorPromotionBenefit, PromotionCampaign


@admin.register(PromotionCampaign)
class PromotionCampaignAdmin(admin.ModelAdmin):
    """운영자 백업용 캠페인 관리입니다."""

    list_display = ("name", "signup_starts_at", "signup_ends_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(InstructorPromotionBenefit)
class InstructorPromotionBenefitAdmin(admin.ModelAdmin):
    """강사별 확정 혜택을 읽기 전용으로 보여 줍니다."""

    list_display = (
        "campaign",
        "instructor",
        "benefit_ends_at",
        "used_tutoring_registration_count",
        "tutoring_registration_limit",
    )
    list_select_related = ("campaign", "instructor__user")
    readonly_fields = (
        "campaign",
        "instructor",
        "benefit_starts_at",
        "benefit_ends_at",
        "tutoring_registration_limit",
        "tutoring_commission_rate_bps",
        "lecture_settlement_fee_rate_bps",
        "used_tutoring_registration_count",
        "created_at",
    )

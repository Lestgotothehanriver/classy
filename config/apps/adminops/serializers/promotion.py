"""출시 프로모션 관리자 API 직렬화기입니다."""

from rest_framework import serializers

from config.apps.promotions.models import InstructorPromotionBenefit, PromotionCampaign


class PromotionCampaignSerializer(serializers.ModelSerializer):
    """관리 웹의 캠페인 생성·수정·현황 응답입니다."""

    benefit_count = serializers.IntegerField(read_only=True)
    tutoring_use_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PromotionCampaign
        fields = [
            "id",
            "name",
            "signup_starts_at",
            "signup_ends_at",
            "is_active",
            "benefit_months",
            "tutoring_registration_limit",
            "tutoring_commission_rate_bps",
            "lecture_settlement_fee_rate_bps",
            "benefit_count",
            "tutoring_use_count",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """가입 기간과 정책 값의 유효 범위를 검증합니다."""
        starts_at = attrs.get("signup_starts_at", getattr(self.instance, "signup_starts_at", None))
        ends_at = attrs.get("signup_ends_at", getattr(self.instance, "signup_ends_at", None))
        if starts_at is not None and ends_at is not None and starts_at > ends_at:
            raise serializers.ValidationError({"signup_ends_at": "종료 시각은 시작 시각 이후여야 합니다."})
        if attrs.get("benefit_months", getattr(self.instance, "benefit_months", 3)) < 1:
            raise serializers.ValidationError({"benefit_months": "혜택 기간은 1개월 이상이어야 합니다."})
        return attrs


class PromotionBenefitSerializer(serializers.ModelSerializer):
    """캠페인별 대상 강사와 사용 현황입니다."""

    instructor_id = serializers.IntegerField(source="instructor.id", read_only=True)
    user_name = serializers.CharField(source="instructor.user.user_name", read_only=True)
    email = serializers.EmailField(source="instructor.user.email", read_only=True)

    class Meta:
        model = InstructorPromotionBenefit
        fields = [
            "id",
            "instructor_id",
            "user_name",
            "email",
            "benefit_starts_at",
            "benefit_ends_at",
            "tutoring_registration_limit",
            "used_tutoring_registration_count",
            "tutoring_commission_rate_bps",
            "lecture_settlement_fee_rate_bps",
        ]

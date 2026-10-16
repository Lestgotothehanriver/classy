"""출시 프로모션 관리자 API 뷰입니다."""

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView

from config.apps.promotions.models import InstructorPromotionBenefit, PromotionCampaign

from ..permissions import IsSuperAdmin
from ..serializers.promotion import PromotionBenefitSerializer, PromotionCampaignSerializer


class PromotionCampaignListCreateView(ListCreateAPIView):
    """GET/POST /admin-api/v1/promotions/ 캠페인 목록과 생성입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = PromotionCampaignSerializer

    def get_queryset(self):
        """대상자 수와 과외 혜택 사용량을 함께 반환합니다."""
        return PromotionCampaign.objects.annotate(
            benefit_count=Count("benefits", distinct=True),
            tutoring_use_count=Coalesce(Sum("benefits__used_tutoring_registration_count"), 0),
        )


class PromotionCampaignDetailView(RetrieveUpdateAPIView):
    """GET/PATCH /admin-api/v1/promotions/{pk}/ 캠페인 수정입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = PromotionCampaignSerializer

    def get_queryset(self):
        """목록과 동일한 운영 통계를 포함합니다."""
        return PromotionCampaign.objects.annotate(
            benefit_count=Count("benefits", distinct=True),
            tutoring_use_count=Coalesce(Sum("benefits__used_tutoring_registration_count"), 0),
        )


class PromotionBenefitListView(ListAPIView):
    """GET /admin-api/v1/promotions/{pk}/benefits/ 대상 강사 목록입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = PromotionBenefitSerializer

    def get_queryset(self):
        """요청한 캠페인에 귀속된 대상 강사를 최신 가입순으로 반환합니다."""
        return InstructorPromotionBenefit.objects.filter(
            campaign_id=self.kwargs["pk"],
        ).select_related("instructor__user").order_by("-created_at")

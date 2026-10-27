"""관리자 마케팅 템플릿과 예약 FCM 발송 API입니다."""

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.notification.marketing import dispatch_marketing_campaign
from config.apps.notification.models import MarketingPushCampaign, MarketingPushMacro, MarketingPushTemplate

from ..models import AdminActionLog
from ..permissions import IsSuperAdmin
from ..serializers.marketing import (
    MarketingPushCampaignSerializer,
    MarketingPushMacroSerializer,
    MarketingPushTemplateSerializer,
)


def _request_id(request) -> str:
    """[request]의 선택적 운영 추적 ID를 반환합니다."""
    return request.headers.get('X-Request-ID', '')


def _log(request, action: str, target) -> None:
    """[target]에 관한 관리자 변경 이력을 append-only로 기록합니다."""
    AdminActionLog.record(
        admin=request.user,
        action=action,
        target_type=target.__class__.__name__,
        target_id=target.pk,
        metadata={
            'status': getattr(target, 'status', ''),
            'scheduled_at': (
                target.scheduled_at.isoformat()
                if getattr(target, 'scheduled_at', None) is not None
                else None
            ),
        },
        request_id=_request_id(request),
    )


class MarketingPushTemplateListCreateView(ListCreateAPIView):
    """GET/POST /admin-api/v1/marketing/templates/ 템플릿 목록과 생성입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = MarketingPushTemplateSerializer
    queryset = MarketingPushTemplate.objects.select_related('created_by')

    def perform_create(self, serializer):
        """생성자를 기록하고 감사 로그를 남깁니다."""
        template = serializer.save(created_by=self.request.user)
        _log(self.request, 'marketing_template.create', template)


class MarketingPushTemplateDetailView(RetrieveUpdateDestroyAPIView):
    """템플릿의 조회·수정·삭제 API입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = MarketingPushTemplateSerializer
    queryset = MarketingPushTemplate.objects.select_related('created_by')

    def perform_update(self, serializer):
        """수정된 템플릿의 운영 이력을 남깁니다."""
        template = serializer.save()
        _log(self.request, 'marketing_template.update', template)

    def perform_destroy(self, instance):
        """삭제 전 스냅샷으로 운영 이력을 남깁니다."""
        _log(self.request, 'marketing_template.delete', instance)
        instance.delete()


class MarketingPushMacroListCreateView(ListCreateAPIView):
    """GET/POST /admin-api/v1/marketing/macros/ 반복 발송 매크로 목록과 생성입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = MarketingPushMacroSerializer
    queryset = MarketingPushMacro.objects.select_related('created_by')

    def perform_create(self, serializer):
        """생성자를 기록하고 매크로 생성 이력을 남깁니다."""
        macro = serializer.save(created_by=self.request.user)
        _log(self.request, 'marketing_macro.create', macro)


class MarketingPushMacroDetailView(RetrieveUpdateDestroyAPIView):
    """반복 발송 매크로의 조회·수정·활성화·삭제 API입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = MarketingPushMacroSerializer
    queryset = MarketingPushMacro.objects.select_related('created_by')

    def perform_update(self, serializer):
        """수정 또는 활성 상태 변경 이력을 남깁니다."""
        macro = serializer.save()
        _log(self.request, 'marketing_macro.update', macro)

    def perform_destroy(self, instance):
        """삭제 전 감사 로그를 남깁니다."""
        _log(self.request, 'marketing_macro.delete', instance)
        instance.delete()


class MarketingPushCampaignListCreateView(ListCreateAPIView):
    """GET/POST /admin-api/v1/marketing/campaigns/ 발송 목록과 생성입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = MarketingPushCampaignSerializer

    def get_queryset(self):
        """선택적 상태 필터를 적용한 최신 발송 목록을 반환합니다."""
        queryset = MarketingPushCampaign.objects.select_related('created_by')
        requested_status = self.request.query_params.get('status')
        if requested_status in MarketingPushCampaign.Status.values:
            queryset = queryset.filter(status=requested_status)
        return queryset

    def create(self, request, *args, **kwargs):
        """즉시 발송은 생성 직후 동기 처리하고, 미래 시각은 예약으로 남깁니다."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save(created_by=request.user)
        _log(request, 'marketing_campaign.create', campaign)
        if campaign.scheduled_at <= timezone.now():
            campaign = dispatch_marketing_campaign(campaign.pk) or campaign
            _log(request, 'marketing_campaign.dispatch', campaign)
        return Response(
            self.get_serializer(campaign).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )


class MarketingPushCampaignDetailView(RetrieveUpdateAPIView):
    """예약 상태 캠페인의 조회·수정 API입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = MarketingPushCampaignSerializer
    queryset = MarketingPushCampaign.objects.select_related('created_by')

    def perform_update(self, serializer):
        """예약 발송 수정과 감사 로그 기록을 함께 처리합니다."""
        campaign = serializer.save()
        _log(self.request, 'marketing_campaign.update', campaign)


class MarketingPushCampaignCancelView(APIView):
    """예약된 마케팅 발송을 원자적으로 취소합니다."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        """[pk] 캠페인이 예약 상태이면 취소하고 최신 상태를 반환합니다."""
        with transaction.atomic():
            campaign = (
                MarketingPushCampaign.objects.select_for_update()
                .filter(pk=pk)
                .first()
            )
            if campaign is None:
                return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
            if campaign.status != MarketingPushCampaign.Status.SCHEDULED:
                return Response(
                    {'error': '예약 상태의 캠페인만 취소할 수 있습니다.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            campaign.status = MarketingPushCampaign.Status.CANCELLED
            campaign.save(update_fields=['status', 'updated_at'])
        _log(request, 'marketing_campaign.cancel', campaign)
        return Response(MarketingPushCampaignSerializer(campaign).data)

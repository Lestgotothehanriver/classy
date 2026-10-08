from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notice
from .serializers import NoticeDetailSerializer, NoticeExposureSerializer, NoticeListSerializer


class NoticeListView(ListAPIView):
    """GET /notices/ - 게시된 공지 목록을 최신순으로 반환합니다."""

    permission_classes = [AllowAny]
    serializer_class = NoticeListSerializer

    def get_queryset(self):
        return Notice.public_queryset().order_by("-publish_at", "-id")


class NoticeDetailView(RetrieveAPIView):
    """GET /notices/{id}/ - 게시된 공지 상세를 반환합니다."""

    permission_classes = [AllowAny]
    serializer_class = NoticeDetailSerializer

    def get_queryset(self):
        return Notice.public_queryset()


class NoticeExposureView(APIView):
    """GET /notices/exposure/ - 현재 공지 모달 캐러셀 항목을 반환합니다."""

    permission_classes = [AllowAny]

    def get(self, request):
        from django.utils import timezone

        now = timezone.now()
        active = Notice.public_queryset(now).filter(exposure_ends_at__gt=now)
        banners = active.filter(
            exposure_type=Notice.ExposureType.HOME_BANNER
        ).order_by("banner_order", "-publish_at", "-id")[:5]
        carousel_items = list(banners)
        return Response(
            {
                "banners": NoticeExposureSerializer(
                    banners, many=True, context={"request": request}
                ).data,
                "carousel": NoticeExposureSerializer(
                    carousel_items, many=True, context={"request": request}
                ).data,
            }
        )

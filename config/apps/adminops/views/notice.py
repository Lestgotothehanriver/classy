from django.db.models import Q
from django.utils import timezone
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.notice.models import Notice

from ..models import AdminActionLog
from ..permissions import IsSuperAdmin
from ..serializers.notice import AdminNoticeSerializer


def _request_id(request) -> str:
    return request.headers.get("X-Request-ID", "")


def _log(admin, action, notice, request):
    AdminActionLog.record(
        admin=admin,
        action=action,
        target_type="Notice",
        target_id=notice.pk,
        metadata={
            "status": notice.status,
            "publish_at": notice.publish_at.isoformat() if notice.publish_at else None,
            "exposure_type": notice.exposure_type,
        },
        request_id=_request_id(request),
    )


class AdminNoticeListCreateView(ListCreateAPIView):
    """GET/POST /admin-api/v1/notices/ - 공지 운영 목록 및 작성."""

    permission_classes = [IsSuperAdmin]
    serializer_class = AdminNoticeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = Notice.objects.select_related("created_by", "updated_by")
        params = self.request.query_params
        status = params.get("status")
        now = timezone.now()
        if status == "SCHEDULED":
            queryset = queryset.filter(
                status=Notice.PublicationStatus.PUBLISHED, publish_at__gt=now
            )
        elif status == "PUBLISHED":
            queryset = queryset.filter(
                status=Notice.PublicationStatus.PUBLISHED, publish_at__lte=now
            )
        elif status in Notice.PublicationStatus.values:
            queryset = queryset.filter(status=status)
        exposure_type = params.get("exposure_type")
        if exposure_type in Notice.ExposureType.values:
            queryset = queryset.filter(exposure_type=exposure_type)
        query = (params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(summary__icontains=query))
        ordering = params.get("ordering", "-publish_at")
        allowed_ordering = {"publish_at", "-publish_at", "created_at", "-created_at", "updated_at", "-updated_at"}
        return queryset.order_by(ordering if ordering in allowed_ordering else "-publish_at", "-id")

    def perform_create(self, serializer):
        notice = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        _log(self.request.user, "notice.create", notice, self.request)


class AdminNoticeDetailView(RetrieveUpdateAPIView):
    """GET/PATCH /admin-api/v1/notices/{id}/ - 공지 조회 및 수정."""

    permission_classes = [IsSuperAdmin]
    serializer_class = AdminNoticeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Notice.objects.select_related("created_by", "updated_by")

    def perform_update(self, serializer):
        notice = serializer.save(updated_by=self.request.user)
        _log(self.request.user, "notice.update", notice, self.request)


class AdminNoticeUnpublishView(APIView):
    """POST /admin-api/v1/notices/{id}/unpublish/ - 공개 노출을 중단합니다."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        notice = Notice.objects.filter(pk=pk).first()
        if notice is None:
            return Response({"error": "공지사항을 찾을 수 없습니다."}, status=404)
        notice.status = Notice.PublicationStatus.UNPUBLISHED
        notice.updated_by = request.user
        notice.save(update_fields=["status", "updated_by", "updated_at"])
        _log(request.user, "notice.unpublish", notice, request)
        return Response(AdminNoticeSerializer(notice, context={"request": request}).data)

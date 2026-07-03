from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
import logging

logger = logging.getLogger(__name__)

from .serializers import ReportCreateSerializer, ReportResponseSerializer


class ReportCreateAPIView(APIView):
    """
    URL: /report/create/

    POST /report/create/
    인증된 사용자가 다른 사용자를 신고합니다.

    Request:
    {
        "reported_user": 3,
        "evidence_image": null,
        "choices": ["inappropriate_content", "abusive_language", "other"]
    }

    Response (201):
    {
        "id": 1,
        "reporter": 5,
        "reported_user": 3,
        "evidence_image": null,
        "choices": ["inappropriate_content", "abusive_language", "other"],
        "created_at": "2026-03-11T04:25:00Z"
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logger.debug("[BACKEND_DEBUG_REPORT] ReportCreate Attempt - data: %s", request.data)
        serializer = ReportCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        response_serializer = ReportResponseSerializer(report)
        logger.debug("[BACKEND_DEBUG_REPORT] Report SUCCESS - id: %d", report.id)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class InquiryCreateAPIView(APIView):
    """
    URL: /report/inquiry/

    POST /report/inquiry/
    인증된 사용자가 고객센터에 1:1 문의를 남깁니다.

    Request:
    {
        "title": "이름 변경 문의",
        "content": "이름을 개명해서 변경하고 싶습니다."
    }

    Response (201):
    {
        "id": 1,
        "title": "이름 변경 문의",
        "content": "이름을 개명해서 변경하고 싶습니다.",
        "is_resolved": false,
        "created_at": "2026-03-11T04:25:00Z"
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .serializers import InquirySerializer
        
        logger.debug("[BACKEND_DEBUG_REPORT] InquiryCreate Attempt - email: %s", request.user.email)
        serializer = InquirySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save()

        logger.debug("[BACKEND_DEBUG_REPORT] Inquiry SUCCESS - id: %d", inquiry.id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ReportCreateSerializer, ReportResponseSerializer


class ReportCreateAPIView(APIView):
    """
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
        serializer = ReportCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        response_serializer = ReportResponseSerializer(report)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

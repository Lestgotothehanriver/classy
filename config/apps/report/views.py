from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
import logging

logger = logging.getLogger(__name__)

from .serializers import ReportCreateSerializer, ReportResponseSerializer


class ReportCreateAPIView(APIView):
    """
    URL: /report/create/

    인증된 사용자가 다른 사용자를 신고하는 API View입니다.

    POST 요청 시, 신고 대상 유저 ID(reported_user), 신고 유형 리스트(choices), 그리고 증빙 이미지 파일(evidence_image)을 수신하여 신고 내역을 생성합니다.

    Request Body (POST, Multipart/Form-data):
        reported_user (int): 신고 대상 사용자 ID (필수).
        choices (list[str]): 신고 사유 종류 목록 (필수).
        evidence_image (File, optional): 신고 증빙 이미지 파일.

    Returns:
        Response: ReportResponseSerializer 데이터 (HTTP 201 Created)
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

    인증된 사용자가 고객센터에 1:1 문의를 등록하는 API View입니다.

    POST 요청 시, 사용자가 남긴 문의 제목(title)과 본문(content)을 입력받아 1:1 문의 내역을 등록합니다.

    Request Body:
        title (str): 문의 제목 (필수).
        content (str): 문의 본문 내용 (필수).

    Returns:
        Response: InquirySerializer 데이터 (HTTP 201 Created)
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

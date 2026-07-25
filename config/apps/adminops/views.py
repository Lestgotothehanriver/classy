import logging

from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsSuperAdmin
from .serializers import AdminLoginSerializer, AdminUserSerializer

logger = logging.getLogger(__name__)


class AdminLoginAPIView(APIView):
    """관리자 로그인 API.

    URL: ``POST /admin-api/v1/auth/login/``

    이메일·비밀번호로 인증한 뒤 ``is_superuser=True`` 계정만 허용합니다.
    성공 시 DRF 토큰과 관리자 요약 정보를 반환합니다. 이 응답은 Next BFF 만
    수신하며, 토큰은 HttpOnly 세션 쿠키에 보관되어 브라우저로 전달되지 않습니다.

    Returns:
        200: {"token": str, "user": {id, email, user_name, is_superuser}}
        400: 입력 오류
        401: 자격 증명 오류
        403: 슈퍼관리자 아님
    """

    parser_classes = [JSONParser]
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        # 기존 사용자 로그인과 동일한 인증 경로를 사용합니다.
        user = authenticate(request, username=email, password=password)
        if user is None:
            logger.warning("[ADMIN_AUTH] login failed (invalid credentials) email=%s", email)
            return Response({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}, status=401)

        if not (user.is_active and user.is_superuser):
            logger.warning("[ADMIN_AUTH] login denied (not superuser) email=%s", email)
            return Response({"error": "관리자 권한이 없습니다."}, status=403)

        token, _ = Token.objects.get_or_create(user=user)
        logger.info("[ADMIN_AUTH] login success email=%s", user.email)

        return Response(
            {
                "token": token.key,
                "user": AdminUserSerializer(user).data,
            },
            status=200,
        )


class AdminMeAPIView(APIView):
    """현재 세션의 관리자 정보를 반환합니다.

    URL: ``GET /admin-api/v1/auth/me/``

    Next BFF 가 세션 쿠키에 담긴 토큰으로 호출해 세션 유효성과 슈퍼관리자
    권한을 검증하는 용도입니다.
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response(AdminUserSerializer(request.user).data, status=200)

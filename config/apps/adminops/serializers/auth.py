from rest_framework import serializers


class AdminLoginSerializer(serializers.Serializer):
    """관리자 로그인 입력 검증 시리얼라이저입니다."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class AdminUserSerializer(serializers.Serializer):
    """세션 검증/로그인 응답에 쓰이는 관리자 프로필 요약입니다.

    브라우저에는 DRF 토큰을 노출하지 않으며, 이 직렬화 결과만 전달합니다.
    """

    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    user_name = serializers.CharField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)

from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """관리자(``is_superuser=True``)만 허용하는 권한 클래스입니다.

    1차 관리자 웹은 Django ``is_superuser`` 계정만 접근할 수 있습니다.
    운영/정산/상담 역할 분리(RBAC)는 이후 확장 단계에서 도입합니다.
    """

    message = "관리자 권한이 없습니다. 관리자(superuser) 계정으로 로그인해주세요."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_superuser
        )

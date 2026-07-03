from rest_framework import permissions
from config.apps.accounts.models import Student, Instructor

class IsStudentUser(permissions.BasePermission):
    """요청 사용자가 Student인지 검증합니다."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'student_profile'))

class IsInstructorUser(permissions.BasePermission):
    """요청 사용자가 Instructor인지 검증합니다."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'instructor_profile'))


class IsVerifiedInstructor(permissions.BasePermission):
    """
    강사 사용자의 경우 pending_info가 존재하고 그 상태가 VERIFIED 인지 검증합니다.
    SAFE_METHODS(GET, HEAD, OPTIONS 등 조회)는 항상 허용합니다.
    강사가 아닌 사용자(학생 등)는 이 권한 체크에서 무조건 통과(True 반환)됩니다.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        user = request.user
        if not user or not user.is_authenticated:
            return False

        # 강사인 경우 pending_info.status 가 VERIFIED 인지 확인
        if hasattr(user, 'instructor_profile'):
            instructor = user.instructor_profile
            pending_info = getattr(instructor, 'pending_info', None)
            if not pending_info or pending_info.status != 'VERIFIED':
                return False

        return True

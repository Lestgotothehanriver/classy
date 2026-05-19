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

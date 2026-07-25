from django.contrib import admin

from .models import AdminActionLog


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    """감사 로그는 기록 보존용(append-only) 이므로 Django Admin 에서도 읽기 전용으로 노출합니다."""

    list_display = (
        "created_at",
        "admin_email",
        "action",
        "target_type",
        "target_id",
        "request_id",
    )
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("admin_email", "action", "target_type", "target_id", "reason", "request_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

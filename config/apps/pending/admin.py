from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from config.apps.adminops.exceptions import AdminOpsError
from config.apps.adminops.services import instructor_verification as service

from .models import File, PendingInstructor


class FileInline(admin.TabularInline):
    model = File
    extra = 0
    can_delete = False
    fields = ("document_link",)
    readonly_fields = ("document_link",)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="첨부 문서")
    def document_link(self, obj):
        # raw 미디어 URL(/media/files/) 은 차단되어 있으므로, 슈퍼관리자 세션으로
        # 열람 가능한 보호 스트리밍 엔드포인트로 링크합니다.
        if not obj.pk or not obj.pending_file:
            return "-"
        url = reverse(
            "adminops:instructor-verification-document",
            args=[obj.pending_instructor_id, obj.pk],
        )
        return format_html('<a href="{}" target="_blank">{}</a>', url, obj.pending_file.name.split("/")[-1])


@admin.register(PendingInstructor)
class PendingInstructorAdmin(admin.ModelAdmin):
    """학력 인증 대기 건. 승인/반려는 관리자 API 와 동일한 공유 서비스를 호출합니다."""

    list_display = ("id", "instructor_label", "university", "status", "applied_at", "reviewed_at", "reviewed_by")
    list_filter = ("status",)
    search_fields = (
        "instructor_profile__user__email",
        "instructor_profile__user__user_name",
        "instructor_profile__user__first_name",
        "instructor_profile__user__last_name",
        "instructor_profile__university",
    )
    readonly_fields = ("applied_at", "reviewed_at", "reviewed_by", "rejection_reason")
    inlines = [FileInline]
    actions = ["approve_selected", "reject_selected"]

    @admin.display(description="강사")
    def instructor_label(self, obj):
        user = obj.instructor_profile.user
        name = f"{user.first_name}{user.last_name}".strip() or user.user_name
        return f"{name} ({user.email})"

    @admin.display(description="대학")
    def university(self, obj):
        return obj.instructor_profile.university

    @admin.action(description="선택한 인증 승인")
    def approve_selected(self, request, queryset):
        approved = 0
        for pending in queryset:
            try:
                service.approve(pending, admin=request.user)
                approved += 1
            except AdminOpsError as exc:
                self.message_user(request, f"#{pending.pk}: {exc.message}", level=messages.WARNING)
        if approved:
            self.message_user(request, f"{approved}건 승인 완료", level=messages.SUCCESS)

    @admin.action(description="선택한 인증 반려(사유 입력)")
    def reject_selected(self, request, queryset):
        if request.POST.get("apply_reject"):
            reason = (request.POST.get("reason") or "").strip()
            if not reason:
                self.message_user(request, "반려 사유를 입력해야 합니다.", level=messages.ERROR)
                return None
            rejected = 0
            for pending in queryset:
                try:
                    service.reject(pending, admin=request.user, reason=reason)
                    rejected += 1
                except AdminOpsError as exc:
                    self.message_user(request, f"#{pending.pk}: {exc.message}", level=messages.WARNING)
            if rejected:
                self.message_user(request, f"{rejected}건 반려 완료", level=messages.SUCCESS)
            return None

        context = {
            **self.admin_site.each_context(request),
            "title": "인증 반려 사유 입력",
            "queryset": queryset,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/pending/reject_reason.html", context)

from django.contrib import admin
from django.utils.html import format_html

from config.apps.accounts.models import User, Student, Instructor, Subject
from config.apps.pending.models import PendingInstructor, File


# ── File 인라인 (PendingInstructor 상세에서 첨부 파일 확인) ──────────────────
class FileInline(admin.TabularInline):
    model = File
    extra = 0
    readonly_fields = ("file_link",)
    fields = ("file_link",)
    can_delete = False

    def file_link(self, obj):
        if obj.pending_file:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                obj.pending_file.url,
                obj.pending_file.name.split("/")[-1],
            )
        return "-"

    file_link.short_description = "첨부 파일"


# ── PendingInstructor ────────────────────────────────────────────────────────
@admin.register(PendingInstructor)
class PendingInstructorAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_username", "get_email", "status", "applied_at")
    list_filter   = ("status",)
    search_fields = ("instructor_profile__user__username", "instructor_profile__user__email")
    readonly_fields = ("applied_at",)
    ordering      = ("-applied_at",)
    inlines       = [FileInline]

    def get_username(self, obj):
        return obj.instructor_profile.user.username
    get_username.short_description = "강사 아이디"

    def get_email(self, obj):
        return obj.instructor_profile.user.email
    get_email.short_description = "이메일"


# ── User ─────────────────────────────────────────────────────────────────────
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display  = ("id", "username", "email", "user_name", "sex", "region", "is_active", "date_joined")
    list_filter   = ("sex", "is_active", "is_staff")
    search_fields = ("username", "email", "user_name", "phone")
    readonly_fields = ("date_joined", "last_login")
    ordering      = ("-date_joined",)


# ── Student ───────────────────────────────────────────────────────────────────
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_username", "get_email", "get_subjects", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at",)
    ordering      = ("-created_at",)

    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = "아이디"

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = "이메일"

    def get_subjects(self, obj):
        return ", ".join([str(s) for s in obj.subjects.all()])
    get_subjects.short_description = "과목"


# ── Instructor ────────────────────────────────────────────────────────────────
@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_username", "get_email", "university", "department", "is_tutoring", "get_subjects", "created_at")
    list_filter   = ("is_tutoring",)
    search_fields = ("user__username", "user__email", "university", "department")
    readonly_fields = ("created_at",)
    ordering      = ("-created_at",)

    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = "아이디"

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = "이메일"

    def get_subjects(self, obj):
        return ", ".join([str(s) for s in obj.subjects.all()])
    get_subjects.short_description = "과목"


# ── Subject ───────────────────────────────────────────────────────────────────
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display  = ("id", "number", "__str__")
    ordering      = ("number",)
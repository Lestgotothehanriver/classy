from django.contrib import admin

from config.apps.accounts.models import User, Student, Instructor, Subject

# PendingInstructor(학력 인증) 어드민은 config.apps.pending.admin 로 이동했습니다.


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
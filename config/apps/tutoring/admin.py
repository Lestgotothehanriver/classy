from django.contrib import admin
from config.apps.tutoring.models import (
    Region,
    TutoringPost,
    TutoringProposal,
    InstructorInfo,
    InstructorReview,
    StudentReview,
)


# ── Region ────────────────────────────────────────────────────────────────────
@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("id", "number", "__str__")
    ordering     = ("number",)


# ── TutoringPost ──────────────────────────────────────────────────────────────
@admin.register(TutoringPost)
class TutoringPostAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_student", "method", "sex", "field", "cost", "view_count", "is_active")
    list_filter   = ("is_active", "method", "sex", "field")
    search_fields = ("title", "student__user__username", "student__user__email", "region")
    ordering      = ("-id",)

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = "학생"


# ── TutoringProposal ──────────────────────────────────────────────────────────
@admin.register(TutoringProposal)
class TutoringProposalAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_instructor", "get_post_title", "get_student")
    search_fields = (
        "instructor__user__username",
        "tutoring_post__title",
        "tutoring_post__student__user__username",
    )
    ordering = ("-id",)

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"

    def get_post_title(self, obj):
        return obj.tutoring_post.title
    get_post_title.short_description = "공고 제목"

    def get_student(self, obj):
        return obj.tutoring_post.student.user.username
    get_student.short_description = "학생"


# ── InstructorInfo ────────────────────────────────────────────────────────────
@admin.register(InstructorInfo)
class InstructorInfoAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_instructor", "method", "cost", "location")
    list_filter   = ("method",)
    search_fields = ("instructor__user__username", "instructor__user__email", "location")
    ordering      = ("-id",)

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"


# ── InstructorReview ──────────────────────────────────────────────────────────
@admin.register(InstructorReview)
class InstructorReviewAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_instructor", "get_student", "professionalism", "teaching_skill", "punctuality")
    list_filter   = ("professionalism", "teaching_skill", "punctuality")
    search_fields = (
        "instructor__user__username",
        "student__user__username",
        "comment",
    )
    ordering      = ("-id",)

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = "학생"


# ── StudentReview ─────────────────────────────────────────────────────────────
@admin.register(StudentReview)
class StudentReviewAdmin(admin.ModelAdmin):
    list_display  = ("id", "get_student", "get_instructor", "rating")
    list_filter   = ("rating",)
    search_fields = (
        "student__user__username",
        "instructor__user__username",
        "comment",
    )
    ordering      = ("-id",)

    def get_student(self, obj):
        return obj.student.user.username
    get_student.short_description = "학생"

    def get_instructor(self, obj):
        return obj.instructor.user.username
    get_instructor.short_description = "강사"

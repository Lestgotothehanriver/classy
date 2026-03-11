from django.contrib import admin
from .models import Lecture, Comment


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "instructor", "price", "is_preview", "view_count", "created_at")
    list_filter = ("is_preview", "created_at")
    search_fields = ("title",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "lecture", "author", "parent", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content",)

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from config.apps.accounts.models import Instructor, Student, Subject


class Lecture(models.Model):
    """강의 모델."""
    video = models.FileField(upload_to="lectures/videos/")
    thumbnail = models.ImageField(upload_to="lectures/thumbnails/")
    title = models.CharField(max_length=255)
    subjects = models.ManyToManyField(Subject, blank=True, related_name="lectures")
    price = models.PositiveIntegerField(default=0)  # 단위: 캐시 (인앱 화폐)
    instructor = models.ForeignKey(
        Instructor, on_delete=models.CASCADE, related_name="lectures"
    )
    is_preview = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)
    likes = models.ManyToManyField(Student, blank=True, related_name="liked_lectures")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Comment(models.Model):
    """강의 댓글 모델 — parent가 있으면 대댓글(reply), 대대댓글은 불가."""
    lecture = models.ForeignKey(
        Lecture, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecture_comments"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    content = models.TextField()
    referenced_person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referenced_in_comments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        # parent가 같은 lecture에 속하는지 검증
        if self.parent and self.parent.lecture_id != self.lecture_id:
            raise ValidationError("대댓글은 같은 강의의 댓글에만 달 수 있습니다.")
        # 대대댓글 금지: parent가 이미 reply(=parent가 있는 댓글)이면 불가
        if self.parent and self.parent.parent_id is not None:
            raise ValidationError("대댓글에 대한 답글은 허용되지 않습니다.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.author} on {self.lecture}"

from django.db import models
from django.conf import settings


class Notification(models.Model):
    TYPE_CHOICES = [
        ("message", "채팅 메시지"),
        ("tutoring_proposal", "과외 제안"),
        ("tutoring_proposal_student", "과외 요청"),
        ("announcement", "공지사항"),
        ("tutoring_accepted", "과외 수락"),
        ("tutoring_rejected", "과외 거절"),
        
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField()
    data = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.type}] {self.user_id} — {self.title}"
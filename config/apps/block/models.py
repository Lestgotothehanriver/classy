from django.db import models
from django.conf import settings

class Block(models.Model):
    """
    유저 간 차단 정보를 저장하는 모델입니다.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocking_relations",
        help_text="차단을 등록한 유저"
    )
    blocked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_relations",
        help_text="차단당한 유저"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "blocked_user"],
                name="unique_user_block"
            )
        ]

    def __str__(self):
        return f"{self.user} blocked {self.blocked_user}"

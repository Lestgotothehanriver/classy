from django.conf import settings
from django.db import models
from django.utils import timezone


class Notice(models.Model):
    """운영자가 게시하는 공지와 홈 추가 노출 정보를 보관합니다."""

    class PublicationStatus(models.TextChoices):
        DRAFT = "DRAFT", "초안"
        PUBLISHED = "PUBLISHED", "게시"
        UNPUBLISHED = "UNPUBLISHED", "게시 중단"

    class ExposureType(models.TextChoices):
        LIST = "LIST", "목록만"
        HOME_BANNER = "HOME_BANNER", "홈 배너 · 앱 공지 모달"

    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=300)
    content = models.TextField()
    banner_image = models.ImageField(
        upload_to="notices/banners/", blank=True, null=True
    )
    status = models.CharField(
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )
    publish_at = models.DateTimeField(blank=True, null=True, db_index=True)
    exposure_type = models.CharField(
        max_length=20,
        choices=ExposureType.choices,
        default=ExposureType.LIST,
        db_index=True,
    )
    exposure_ends_at = models.DateTimeField(blank=True, null=True, db_index=True)
    banner_order = models.PositiveSmallIntegerField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notices",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_notices",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publish_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "publish_at"]),
            models.Index(fields=["exposure_type", "exposure_ends_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def effective_status(self) -> str:
        """현재 서버 시간 기준으로 관리자 UI에 표시할 상태를 반환합니다."""
        if self.status == self.PublicationStatus.DRAFT:
            return "DRAFT"
        if self.status == self.PublicationStatus.UNPUBLISHED:
            return "UNPUBLISHED"
        if self.publish_at and self.publish_at > timezone.now():
            return "SCHEDULED"
        return "PUBLISHED"

    @classmethod
    def public_queryset(cls, now=None):
        """현재 사용자에게 보여도 되는 게시 공지 쿼리셋을 반환합니다."""
        current_time = now or timezone.now()
        return cls.objects.filter(
            status=cls.PublicationStatus.PUBLISHED,
            publish_at__lte=current_time,
        )

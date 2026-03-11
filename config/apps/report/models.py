from django.conf import settings
from django.db import models


class ReportReasonChoices(models.TextChoices):
    """신고 사유 선택지."""
    INAPPROPRIATE_CONTENT = "inappropriate_content", "부적절한 내용"
    FALSE_INFORMATION = "false_information", "허위 정보 기재"
    ABUSIVE_LANGUAGE = "abusive_language", "비속어/폭언"
    EXCESSIVE_REQUEST = "excessive_request", "불합리한/과도한 요구/요청"
    UNREPORTED_CLASS_COMPLETION = "unreported_class_completion", "수업 성사 미신고"
    OTHER = "other", "기타"


class Report(models.Model):
    """사용자 신고 모델."""
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_filed",
        help_text="신고한 사용자",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_received",
        help_text="신고 대상 사용자",
    )
    evidence_image = models.ImageField(
        upload_to="reports/evidence/",
        blank=True,
        null=True,
        help_text="증거 이미지 (선택)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report #{self.pk}: {self.reporter} → {self.reported_user}"


class ReportChoice(models.Model):
    """신고에 연결된 사유 선택 (1:N)."""
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="choices",
    )
    content = models.CharField(
        max_length=50,
        choices=ReportReasonChoices.choices,
        help_text="신고 사유",
    )

    class Meta:
        unique_together = ("report", "content")

    def __str__(self):
        return f"{self.report_id} - {self.get_content_display()}"

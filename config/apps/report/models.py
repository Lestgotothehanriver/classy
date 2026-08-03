from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class ReportReasonChoices(models.TextChoices):
    """신고 사유 선택지."""
    INAPPROPRIATE_CONTENT = "inappropriate_content", "부적절한 내용"
    FALSE_INFORMATION = "false_information", "허위 정보 기재"
    ABUSIVE_LANGUAGE = "abusive_language", "비속어/폭언"
    EXCESSIVE_REQUEST = "excessive_request", "불합리한/과도한 요구/요청"
    UNREPORTED_CLASS_COMPLETION = "unreported_class_completion", "수업 성사 미신고"
    OTHER = "other", "기타"


class ReportSourceChoices(models.TextChoices):
    """신고 맥락(어디서/무엇을 신고했는가). 모든 신고에 항상 기록된다.

    뭉뚱그린 ``USER`` 값은 두지 않는다 — 채팅·프로필도 각자 맥락을 유지해야
    관리자가 "무엇에 대한 신고인지"를 잃지 않는다.
    """
    TEACHER_PROFILE = "teacher_profile", "강사 프로필"
    CHAT = "chat", "채팅"
    LECTURE = "lecture", "영상(강의)"
    COMMENT = "comment", "댓글"
    TUTORING_POST = "tutoring_post", "과외 공고"


class ReportStatusChoices(models.TextChoices):
    """관리자 처리 상태. PENDING → IN_REVIEW → RESOLVED/DISMISSED (종결)."""
    PENDING = "pending", "미처리"
    IN_REVIEW = "in_review", "보류(검토중)"
    RESOLVED = "resolved", "조치완료"
    DISMISSED = "dismissed", "무혐의(기각)"


class Report(models.Model):
    """사용자 신고 모델.

    ``reported_user`` 는 언제나 책임 주체(제재 대상)이며, 콘텐츠 신고의 경우
    서버가 콘텐츠 소유자로부터 도출한다. ``source`` 는 신고 맥락을,
    ``content_object`` (GenericFK)는 열람 대상(영상/댓글/공고/프로필)을 가리킨다.
    채팅 신고는 개인정보 보호를 위해 ``content_object`` 를 저장하지 않는다.
    """
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
        help_text="신고 대상 사용자(콘텐츠 신고는 소유자로 도출)",
    )
    source = models.CharField(
        max_length=30,
        choices=ReportSourceChoices.choices,
        default=ReportSourceChoices.TEACHER_PROFILE,
        db_index=True,
        help_text="신고 맥락(강사프로필/채팅/영상/댓글/공고)",
    )
    description = models.TextField(
        blank=True,
        help_text="신고자가 남긴 자유서술",
    )
    evidence_image = models.ImageField(
        upload_to="reports/evidence/",
        blank=True,
        null=True,
        help_text="증거 이미지 (선택)",
    )

    # 열람 대상(콘텐츠) 참조 — GenericFK. 채팅/미지정 신고는 비어 있다.
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # 관리자 처리 상태 및 결과
    status = models.CharField(
        max_length=20,
        choices=ReportStatusChoices.choices,
        default=ReportStatusChoices.PENDING,
        db_index=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_resolved",
        help_text="처리한 관리자",
    )
    resolution_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reported_user", "status"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

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


class Inquiry(models.Model):
    """고객센터 1:1 문의 모델"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inquiries",
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Inquiry #{self.pk}: {self.title} by {self.user.email}"

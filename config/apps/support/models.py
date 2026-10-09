"""운영 조치가 필요한 고객 문의 티켓 모델입니다."""

from django.conf import settings
from django.db import models


class SupportTicket(models.Model):
    """고객과 운영자가 공유하는 1:1 문의의 단일 상태 원본입니다."""

    class TicketType(models.TextChoices):
        NAME_CHANGE = "NAME_CHANGE", "이름 변경"
        CASH_PAYMENT = "CASH_PAYMENT", "캐시·결제"
        TUTORING_FEE = "TUTORING_FEE", "성사 수수료"
        PAYBACK = "PAYBACK", "페이백"
        VERIFICATION_PROFILE = "VERIFICATION_PROFILE", "인증·프로필"
        LEGACY = "LEGACY", "기존 문의"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "접수"
        IN_PROGRESS = "IN_PROGRESS", "처리 중"
        WAITING_FOR_USER = "WAITING_FOR_USER", "추가 정보 필요"
        RESOLVED = "RESOLVED", "해결"
        CLOSED = "CLOSED", "종결"

    class RelatedKind(models.TextChoices):
        PURCHASE = "PURCHASE", "구매 내역"
        TUTORING_REGISTRATION = "TUTORING_REGISTRATION", "성사등록"
        INSTRUCTOR_VERIFICATION = "INSTRUCTOR_VERIFICATION", "학력 인증"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_tickets",
    )
    requester_name = models.CharField(max_length=80, blank=True)
    requester_role = models.CharField(max_length=20, blank=True)
    ticket_type = models.CharField(max_length=30, choices=TicketType.choices, db_index=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.RECEIVED, db_index=True
    )
    title = models.CharField(max_length=255)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_support_tickets",
    )
    related_kind = models.CharField(max_length=40, choices=RelatedKind.choices, blank=True)
    related_id = models.PositiveBigIntegerField(null=True, blank=True)
    requested_last_name = models.CharField(max_length=150, blank=True)
    requested_first_name = models.CharField(max_length=150, blank=True)
    name_change_reason = models.TextField(blank=True)
    last_admin_message_at = models.DateTimeField(null=True, blank=True)
    last_user_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "ticket_type", "updated_at"]),
            models.Index(fields=["assigned_to", "status", "updated_at"]),
            models.Index(fields=["related_kind", "related_id"]),
        ]

    def __str__(self) -> str:
        return f"SupportTicket #{self.pk}: {self.ticket_type}"


class SupportMessage(models.Model):
    """티켓 공개 대화와 운영자 내부 메모를 보관합니다."""

    class SenderKind(models.TextChoices):
        USER = "USER", "사용자"
        ADMIN = "ADMIN", "운영자"
        SYSTEM = "SYSTEM", "시스템"

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    sender_name = models.CharField(max_length=80, blank=True)
    sender_kind = models.CharField(max_length=15, choices=SenderKind.choices)
    content = models.TextField()
    is_internal = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]


class SupportAttachment(models.Model):
    """티켓 메시지에 딸린 보호 첨부 파일입니다."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey(
        SupportMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments"
    )
    file = models.FileField(upload_to="support/%Y/%m/")
    original_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class SupportEvent(models.Model):
    """상태·담당자·업무 처리 액션의 변경 이력입니다."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=80, blank=True)
    event_type = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]

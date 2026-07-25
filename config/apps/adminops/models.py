from django.conf import settings
from django.db import models


class AdminActionLog(models.Model):
    """관리자 운영 액션에 대한 append-only 감사 로그입니다.

    정산 완료/취소, 학력 인증 승인/반려, 수수료 확인, 신고 처리, 문의 답변 등
    상태를 바꾸는 모든 관리자 액션은 이 로그에 한 건씩 기록됩니다. 레코드는
    생성 후 수정·삭제되지 않으며(append-only), 관리자 계정이 삭제되더라도
    로그 자체는 보존됩니다.

    Attributes:
        admin (User): 액션을 수행한 관리자. 계정 삭제 시 NULL 로 남지만 로그는 유지됩니다.
        admin_email (str): 삭제/변경에 대비한 관리자 이메일 스냅샷.
        action (str): 액션 식별자. 예) "settlement.complete", "instructor.reject".
        target_type (str): 대상 모델명. 예) "SettlementRecord".
        target_id (str): 대상 PK(문자열 보관으로 비정수 PK 도 허용).
        reason (str): 관리자가 입력한 처리 사유.
        metadata (dict): 이전/이후 상태 등 부가 정보 스냅샷.
        request_id (str): 요청 추적용 ID(가능한 경우).
        created_at (datetime): 기록 시각.
    """

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_action_logs",
    )
    admin_email = models.EmailField(blank=True)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True, db_index=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.admin_email or self.admin_id} {self.action} {self.target_type}#{self.target_id}"

    def save(self, *args, **kwargs):
        """append-only 보장: 이미 저장된 레코드는 다시 저장(수정)할 수 없습니다."""
        if self.pk is not None:
            raise ValueError("AdminActionLog is append-only and cannot be modified.")
        # 관리자 이메일 스냅샷을 자동 보관합니다.
        if not self.admin_email and self.admin_id and getattr(self.admin, "email", ""):
            self.admin_email = self.admin.email
        super().save(*args, **kwargs)

    @classmethod
    def record(
        cls,
        *,
        admin,
        action,
        target_type="",
        target_id="",
        reason="",
        metadata=None,
        request_id="",
    ):
        """감사 로그 한 건을 기록하고 반환합니다.

        서비스 계층에서 상태 변경과 같은 트랜잭션 안에서 호출하는 것을 권장합니다.
        """
        return cls.objects.create(
            admin=admin,
            admin_email=getattr(admin, "email", "") or "",
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id != "" else "",
            reason=reason or "",
            metadata=metadata or {},
            request_id=request_id or "",
        )

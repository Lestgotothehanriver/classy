from django.db import models
from django.conf import settings


class DeviceToken(models.Model):
    """
    모바일 푸시 알림(FCM 등) 발송을 위한 사용자별 '기기 토큰' 데이터를 관리하는 모델입니다.
    
    사용자가 여러 대의 스마트폰/태블릿을 사용할 수 있으므로 User와 M:1 관계로 설계되었습니다.
    토큰은 고유(unique)해야 하며, 중복 토큰 등록 시 이전 소유자의 토큰은 자동 삭제됩니다.
    
    Attributes:
        user (ForeignKey): 기기 토큰을 등록한 사용자.
        token (str): 기기에 발급된 고유 푸시 식별자(문자열).
        platform (str): 토큰이 발급된 단말기 OS 플랫폼 (ios, android, web).
        is_active (bool): 해당 기기로 푸시 알림 수신 동의 여부 (앱 내 설정).
        updated_at (DateTimeField): 토큰이 마지막으로 갱신되거나 등록된 일시.
    """
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web'),
    ]
    ACTIVE_ROLE_CHOICES = [
        ('student', '학생'),
        ('instructor', '선생님'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_tokens',
    )
    token = models.CharField(max_length=500, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='android')
    is_active = models.BooleanField(default=True)  # 사용자가 알림 off 시 False
    is_chat_active = models.BooleanField(default=True)
    # 이 토큰이 마지막으로 앱에서 사용한 역할입니다. 마케팅 발송은 역할이 확인된
    # 활성 토큰으로만 제한해, 겸업 계정의 다른 역할 단말에 중복 발송하지 않습니다.
    active_role = models.CharField(
        max_length=20,
        choices=ACTIVE_ROLE_CHOICES,
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(
                fields=['is_active', 'active_role'],
                name='notificatio_is_acti_2dd9e3_idx',
            ),
        ]

    def __str__(self):
        return f"{self.user.email} | {self.platform} | active={self.is_active}"


class Notification(models.Model):
    """
    플랫폼 내 하단 알림 탭(Notification Center)에 표시되는 '인앱 알림' 모델입니다.
    
    모바일 단말기로 발송되는 Push 알림과 별개로 앱 내 DB에 저장되어 영구 기록되며,
    '학생' 혹은 '강사' 중 어느 역할(Role)에게 발송된 알림인지 구분하여 필터링할 수 있습니다.
    
    Attributes:
        user (ForeignKey): 알림을 수신할 대상 사용자.
        type (str): 알림의 종류 (예: 'tutoring_request', 'new_comment', 'payment_success' 등).
        role (str): 수신자의 역할 필터 ('student' 또는 'instructor').
        title (str): 알림 제목.
        body (str): 알림 상세 내용.
        data (JSONField): 클릭 시 특정 화면으로 이동하기 위한 부가 데이터 (id, url 등).
        is_read (bool): 사용자가 해당 알림을 읽었는지(클릭했는지) 여부.
        created_at (DateTimeField): 알림 발송(생성) 일시.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type = models.CharField(max_length=50)
    role = models.CharField(max_length=20, default='instructor')  # 'student' | 'instructor'
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.type}] {self.title} → {self.user.email}"


class MarketingPushTemplate(models.Model):
    """관리자가 재사용하는 마케팅 알림 제목·본문 템플릿입니다."""

    name = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_marketing_push_templates',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self) -> str:
        """관리 화면에 표시할 템플릿 이름을 반환합니다."""
        return self.name


class MarketingPushMacro(models.Model):
    """KST 기준으로 반복 실행되어 개별 캠페인을 만드는 마케팅 발송 매크로입니다."""

    class Recurrence(models.TextChoices):
        """매크로 실행 반복 단위입니다."""

        DAILY = 'DAILY', '매일'
        WEEKLY = 'WEEKLY', '매주'
        MONTHLY = 'MONTHLY', '매월'

    name = models.CharField(max_length=100, unique=True)
    target_role = models.CharField(
        max_length=20,
        choices=[
            ('student', '학생'), ('instructor', '선생님'), ('all', '전체'),
        ],
        default='all',
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    push_only = models.BooleanField(default=True)
    recurrence = models.CharField(max_length=16, choices=Recurrence.choices)
    scheduled_time = models.TimeField(help_text='Asia/Seoul 기준 실행 시각')
    weekday = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='매주 발송의 요일입니다. 월요일은 0, 일요일은 6입니다.',
    )
    day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='매월 발송의 일자입니다. 해당 월에 없으면 말일에 발송합니다.',
    )
    next_scheduled_at = models.DateTimeField(db_index=True)
    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_marketing_push_macros',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']
        indexes = [
            models.Index(
                fields=['is_active', 'next_scheduled_at'],
                name='notificatio_macro_due_idx',
            ),
        ]

    def __str__(self) -> str:
        """관리 화면에 표시할 매크로 이름을 반환합니다."""
        return self.name


class MarketingPushCampaign(models.Model):
    """예약 또는 즉시 발송하는 마케팅 FCM 캠페인의 불변 발송 스냅샷입니다."""

    class TargetRole(models.TextChoices):
        """캠페인의 단말 활성 역할 대상입니다."""

        STUDENT = 'student', '학생'
        INSTRUCTOR = 'instructor', '선생님'
        ALL = 'all', '전체'

    class Status(models.TextChoices):
        """예약 발송 처리 상태입니다."""

        SCHEDULED = 'SCHEDULED', '예약됨'
        SENDING = 'SENDING', '발송 중'
        COMPLETED = 'COMPLETED', '완료'
        FAILED = 'FAILED', '실패'
        CANCELLED = 'CANCELLED', '취소됨'

    target_role = models.CharField(
        max_length=20,
        choices=TargetRole.choices,
        default=TargetRole.ALL,
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    scheduled_at = models.DateTimeField(db_index=True)
    push_only = models.BooleanField(default=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    failure_detail = models.TextField(blank=True)
    macro = models.ForeignKey(
        MarketingPushMacro,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_marketing_push_campaigns',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_at', '-id']
        indexes = [
            models.Index(
                fields=['status', 'scheduled_at'],
                name='notificatio_status_96a662_idx',
            ),
        ]

    def __str__(self) -> str:
        """감사 로그와 관리자 목록용 식별자를 반환합니다."""
        return f'#{self.pk} {self.title}'

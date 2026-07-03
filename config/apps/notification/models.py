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

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_tokens',
    )
    token = models.CharField(max_length=500, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='android')
    is_active = models.BooleanField(default=True)  # 사용자가 알림 off 시 False
    is_chat_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'is_active'])]

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

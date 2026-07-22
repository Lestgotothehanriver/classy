from django.conf import settings
#________________________________________________________________

from django.db import models
from django.db.models import Q
#________________________________________________________________

# 커스텀 유저 모델을 불러오기 위한 설정값. 보통은 auth.User 또는 직접 정의한 User 모델이 됨
from django.conf import settings
User = settings.AUTH_USER_MODEL

#_______________________________________________________________________
# ✅ ChatRoom 모델: DM 또는 그룹 채팅방
#_______________________________________________________________________
class ChatRoom(models.Model):
    """
    학생과 강사 간의 1:1 과외 문의 및 실시간 소통을 위한 '채팅방' 모델입니다.
    
    특정 과외 공고(TutoringPost)를 매개로 생성되며, 제안자가 보낸 최초 메시지에 대해
    상대방(counterparty)이 수락(첫 답장)을 해야만 양방향 소통이 활성화됩니다(is_accepted=True).
    
    Attributes:
        student (ForeignKey): 채팅방에 참여 중인 학생.
        instructor (ForeignKey): 채팅방에 참여 중인 강사.
        post (ForeignKey): 채팅방 생성의 계기가 된 과외 구인 공고.
        title (str): 채팅방 제목 (필요 시 노출).
        initiated_by (ForeignKey): 먼저 제안(대화)을 시작한 유저.
        is_accepted (bool): 상대방이 첫 답장을 보내어 제안을 수락했는지 여부.
        liked_by (ManyToManyField): 채팅방을 찜/즐겨찾기한 유저 목록.
        muted_by (ManyToManyField): 채팅방 알림을 끈 유저 목록.
        created_at (DateTimeField): 채팅방 생성 일시.
    """
    student = models.ForeignKey('accounts.Student', related_name="chat_rooms", on_delete=models.CASCADE)
    instructor = models.ForeignKey('accounts.Instructor', related_name="chat_rooms", on_delete=models.CASCADE)
    post = models.ForeignKey('tutoring.TutoringPost', related_name="chat_rooms", on_delete=models.CASCADE)

    title = models.CharField(max_length=255, blank=True)

    # 제안/요청을 시작한 유저 (상대방 = counterparty)
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='initiated_rooms',
    )

    # 상대방이 첫 답장을 보냈는지 (수락 여부)
    is_accepted  = models.BooleanField(default=False)

    liked_by = models.ManyToManyField(User, related_name="liked_chat_rooms", blank=True)
    muted_by = models.ManyToManyField(User, related_name="muted_chat_rooms", blank=True)

    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'instructor', 'post'], name='unique_chat_room')
        ]

    def __str__(self):
        return self.title or f"Room {self.pk}"


#_______________________________________________________________________
# ✅ ChatMessage 모델: 채팅방 안의 메시지
#_______________________________________________________________________
class ChatMessage(models.Model):
    """
    채팅방(ChatRoom) 내에서 오고 간 개별 '채팅 메시지' 모델입니다.
    
    텍스트 외에도 이미지가 첨부될 수 있으며, M:N 관계인 read_by 필드를 통해
    채팅방 참여자 중 누가 이 메시지를 읽었는지(읽음 처리/안읽은 뱃지 카운트)를 추적합니다.
    
    Attributes:
        room (ForeignKey): 메시지가 전송된 대상 채팅방.
        sender (ForeignKey): 메시지를 발송한 유저.
        text (str): 메시지 텍스트 내용 (이미지만 보낼 경우 빈 문자열 가능).
        read_by (ManyToManyField): 이 메시지를 읽은 유저 목록 (보낸 사람은 자동 추가됨).
        created_at (DateTimeField): 메시지 발송 일시.
    """
    room = models.ForeignKey(ChatRoom, related_name="messages",
                             on_delete=models.CASCADE)
    # 이 메시지가 어떤 채팅방에 속해 있는지

    sender = models.ForeignKey(User, related_name="sent_messages",
                               on_delete=models.CASCADE)
    # 누가 보낸 메시지인지

    text = models.TextField(blank=True)
    # 메시지 텍스트. 파일만 보낼 수도 있어서 blank=True

    read_by = models.ManyToManyField(User, blank=True,
                                     related_name="read_messages")
    # 이 메시지를 읽은 유저들 목록 (읽음 처리용)

    created_at = models.DateTimeField(auto_now_add=True)
    # 메시지가 생성된 시간

    class Meta:
        ordering = ("created_at",)
        # 메시지 가져올 때 오래된 순서로 정렬됨 (room.messages.all() 하면 자동 정렬)

    def save(self, *args, **kwargs):
        is_new = self.pk is None  # 아직 저장되지 않은 새 메시지인지 확인
        super().save(*args, **kwargs)

        if is_new:
            # 새 메시지라면, 보낸 사람은 자동으로 '읽은 사람 목록'에 추가
            self.read_by.add(self.sender)

#_______________________________________________________________________
# ✅ Image 모델: 채팅방에서 사용되는 이미지 첨부
#_______________________________________________________________________
class Image(models.Model):
    """
    채팅 메시지(ChatMessage)에 다중으로 첨부될 수 있는 '이미지 파일' 모델입니다.
    
    메시지 전송 시 텍스트와 함께, 또는 사진만 단독으로 전송할 때 사용되며
    미디어 서버(S3 등)에 업로드된 경로를 저장합니다.
    
    Attributes:
        message (ForeignKey): 이미지가 첨부된 부모 채팅 메시지.
        image (ImageField): 실제 업로드된 이미지 파일.
        uploaded_at (DateTimeField): 이미지 업로드 일시.
    """
    message = models.ForeignKey(ChatMessage, related_name="images",
                             on_delete=models.CASCADE, null=True, blank=True)
    # 이 이미지가 어떤 채팅방에 속하는지

    image = models.ImageField(upload_to="chat/images/")
    # 이미지 파일. 업로드 경로 지정

    uploaded_at = models.DateTimeField(auto_now_add=True)
    # 이미지 업로드 시간

#_______________________________________________________________________
# ✅ UserDeviceToken 모델: 사용자 디바이스 토큰, 단말 푸시 토큰을 저장한다
#_______________________________________________________________________
class UserDeviceToken(models.Model):
    """
    FCM(Firebase Cloud Messaging) 등 모바일 푸시 알림 발송을 위한
    '사용자 기기 토큰'을 관리하는 모델입니다.
    
    기기 변경 및 토큰 갱신 시 업데이트되며, 알림 수신 동의 여부(is_active)를 제어합니다.
    
    Attributes:
        user (OneToOneField): 토큰을 소유한 사용자.
        token (str): 기기에 발급된 고유 푸시 토큰 문자열.
        platform (str): 단말기 OS 플랫폼 (예: 'android', 'ios').
        is_active (bool): 해당 기기로 푸시 알림 발송 허용 여부.
        created_at (DateTimeField): 토큰 최초 등록 일시.
        updated_at (DateTimeField): 토큰 최종 갱신 일시.
    """
    user = models.OneToOneField(User, related_name="device_token",
                                  on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_chat_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id}:{self.platform}"


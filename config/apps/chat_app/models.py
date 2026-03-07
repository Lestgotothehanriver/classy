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
    student = models.ForeignKey('accounts.Student', related_name="chat_rooms", on_delete=models.CASCADE)
    instructor = models.ForeignKey('accounts.Instructor', related_name="chat_rooms", on_delete=models.CASCADE)
    post = models.ForeignKey('tutoring.TutoringPost', related_name="chat_rooms", on_delete=models.CASCADE)

    title        = models.CharField(max_length=255, blank=True)
    # 그룹방 이름. DM이면 비워둘 수도 있음

    created_at   = models.DateTimeField(auto_now_add=True)
    # 채팅방이 생성된 시간

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'instructor', 'post'], name='unique_chat_room')
        ]

    def __str__(self):
        return self.title or f"Room {self.pk}"
        # 제목이 있으면 제목, 없으면 "Room 1"처럼 출력


#_______________________________________________________________________
# ✅ ChatMessage 모델: 채팅방 안의 메시지
#_______________________________________________________________________
class ChatMessage(models.Model):
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
    채팅방에서 사용되는 이미지 첨부 모델
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
    user = models.OneToOneField(User, related_name="device_token",
                                  on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id}:{self.platform}"


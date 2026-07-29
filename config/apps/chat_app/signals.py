# 새 메시지가 DB에 생기면 “누구에게 푸시를 보낼지”를 백엔드에서 자동으로 판단해서 push_to_users()로 보냄
# 규칙: 보낸 사람 제외, 그 방에 “현재 웹소켓으로 접속 중”인 사람 제외, 참여자만 대상.

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache

from .models import ChatMessage
from .notifications import push_to_users
from django.db.models import Count, Q

PRESENCE_KEY = "chat:room:{room_id}:online"

def room_online_ids(room_id: int) -> set:
    """
    채팅방의 온라인 유저 ID를 Redis에서 가져옴
    """
    key = PRESENCE_KEY.format(room_id=room_id)
    return set(cache.get(key) or [])

# receiver는 시그널 리스너를 등록하는 데코레이터
# 이 함수는 특정 시그널이 발생 할 때 자동으로 실행되라고 알려주는 표시
# 인자: 어떤 시그널을 받을 지 지정, post_save: 모델 저장 후, pre_delete: 모델 삭제 전 등
@receiver(post_save, sender=ChatMessage)
def notify_new_message(sender, instance: ChatMessage, created: bool, **kwargs):
    """
    새 메시지가 저장될 때 호출되는 시그널 리스너
    """
    if not created:
        return
    # instance는 새로 생성된 ChatMessage 객체
    room = instance.room
    sender_id = instance.sender_id
    online = room_online_ids(room.id)
    participants = [room.student.user, room.instructor.user]
    participants_ids = {u.id for u in participants}
    
    non_active_user_ids = []
    muted_user_ids = set(room.muted_by.values_list('id', flat=True))
    for u in participants:
         # Query device_tokens for the user and determine if they have disabled notifications.
         # If they have device tokens, but all of them are inactive (either is_active=False or is_chat_active=False),
         # we consider them as inactive/disabled for chat notifications.
         tokens = u.device_tokens.all()
         if tokens.exists() and not any(t.is_active and getattr(t, 'is_chat_active', True) for t in tokens):
             non_active_user_ids.append(u.id)

    targets = participants_ids - {sender_id} - online - set(non_active_user_ids) - muted_user_ids
    if not targets:
        return

    title = room.title 
    body = instance.text or "새 이미지가 도착했습니다."
    data = {
        "type": "message",
        "room_id": str(room.id),
        "msg_id": str(instance.id),
        "sender_id": str(sender_id),
    }
    # 채팅 메시지는 인앱 Notification(알림함)에 쌓지 않는다.
    # 메시지는 계속 누적되므로 알림함이 오염되기 때문. 알림함은 과외 문의/제안/수락 등
    # 실제 '이벤트'만 담고, 채팅 메시지는 FCM 푸시로만 전달한다.
    # (채팅방 내 실시간 수신은 chat_app.consumers 의 chat_{room_id} 그룹이 담당하므로 영향 없음)
    result = push_to_users(targets, title=title, body=body, username=instance.sender.username, data=data)





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
    for u in participants:
         # device_token 역참조나 다른 관련된 로직 활용
         # 일단은 hasattr로 방어 코드 작성 (User 모델에 device_token이 OneToOne으로 연결되어 있다고 가정)
         if hasattr(u, 'device_token') and not u.device_token.is_active:
             non_active_user_ids.append(u.id)

    targets = participants_ids - {sender_id} - online - set(non_active_user_ids)
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
    result = push_to_users(targets, title=title, body=body, username=instance.sender.username, data=data)
    #print(f"Sent push notification to {len(targets)} users in room {room.id} for new message {instance.id}.")



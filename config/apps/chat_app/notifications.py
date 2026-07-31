import logging
from typing import Iterable, Dict, Any
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from config.apps.notification.fcm import send_push_to_user
from .services import count_unread_messages, get_participant_role

logger = logging.getLogger(__name__)


def broadcast_chat_summary(message) -> None:
    """Broadcast one authoritative chat-room summary to both participants."""
    try:
        room = message.room
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        sender_name = (
            getattr(message.sender, "user_name", None)
            or message.sender.username
        )
        for user in (room.student.user, room.instructor.user):
            target_role = get_participant_role(room, user)
            if target_role is None:
                continue
            async_to_sync(channel_layer.group_send)(
                f"notification_user_{user.id}",
                {
                    "type": "chat.summary",
                    "room_id": str(room.id),
                    "msg_id": str(message.id),
                    "text": message.text or "새 이미지가 도착했습니다.",
                    "created_at": message.created_at.isoformat(),
                    "sender_id": str(message.sender_id),
                    "sender_name": sender_name,
                    "target_role": target_role,
                    "unread_count": count_unread_messages(
                        room_id=room.id,
                        user=user,
                    ),
                },
            )
    except Exception:
        logger.exception(
            "Failed to broadcast chat summary for message %s",
            message.id,
        )


def broadcast_chat_read_state(*, room, message_id, reader) -> None:
    """Broadcast the reader's authoritative room unread count to their devices."""
    try:
        channel_layer = get_channel_layer()
        target_role = get_participant_role(room, reader)
        if channel_layer is None or target_role is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"notification_user_{reader.id}",
            {
                "type": "chat.read_state",
                "room_id": str(room.id),
                "message_id": str(message_id),
                "reader_id": str(reader.id),
                "target_role": target_role,
                "unread_count": count_unread_messages(
                    room_id=room.id,
                    user=reader,
                ),
            },
        )
    except Exception:
        logger.exception(
            "Failed to broadcast chat read state room=%s reader=%s",
            room.id,
            reader.id,
        )


def push_to_users(user_ids: Iterable[int], title: str, body: str, username: str,
                  data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    채팅방 참여자 중 알림 대상(user_ids)에게 FCM 푸시 전송.
    기존 UserDeviceToken 대신 notification.DeviceToken 모델을 조회하고 
    Firebase Admin SDK를 활용하는 notification.fcm.send_push_to_user를 재사용합니다.
    """
    User = get_user_model()
    users = list(User.objects.filter(id__in=user_ids))
    if not users:
        return {"success": 0, "failure": 0, "detail": "no users found"}

    payload_data = (data or {}).copy()
    payload_data["username"] = username

    for user in users:
        try:
            send_push_to_user(user, title, body, payload_data)
        except Exception as e:
            logger.error(f"Failed to send chat push to user {user.id}: {e}")

    return {"success": len(users), "failure": 0, "detail": "dispatched to notification.fcm"}

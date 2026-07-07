import logging
from typing import Iterable, Dict, Any
from django.contrib.auth import get_user_model
from config.apps.notification.fcm import send_push_to_user

logger = logging.getLogger(__name__)

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


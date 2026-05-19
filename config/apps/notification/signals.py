"""
알림 시그널 모음.

════════════════════════════════════════════════════════════════════════════════
1. Notification post_save: WebSocket 브로드캐스트 처리
2. PendingInstructor post_save: 강사 승인/반려 알림 생성
════════════════════════════════════════════════════════════════════════════════
"""
import logging

from asgiref.sync import async_to_sync
from django.db.models.signals import post_save
from django.dispatch import receiver

from config.apps.pending.models import PendingInstructor

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
# 시그널 핸들러
# ════════════════════════════════════════════════════════════════════════════════

@receiver(post_save, sender='notification.Notification')
def broadcast_notification_on_save(sender, instance, created, **kwargs):
    """
    Notification 객체 생성 시 WebSocket으로 브로드캐스트합니다.

    Args:
        sender: 모델 클래스
        instance: 생성된 알림 인스턴스
        created: 객체 생성 여부
        **kwargs: 기타 인자
    """
    if not created:
        return  # 수정 이벤트는 무시

    try:
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        group_name = f"notification_user_{instance.user_id}"
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notification.new",
                "id": instance.id,
                "ntype": instance.type,
                "role": instance.role,
                "title": instance.title,
                "body": instance.body,
                "data": instance.data,
                "created_at": instance.created_at.isoformat(),
            },
        )
        logger.debug(f"*** [Signal] WS broadcast sent → user_id={instance.user_id} type={instance.type} ***")
    except Exception as e:
        logger.error(f"*** [Signal] WebSocket broadcast failed: {e} ***")


# ─── 2) PendingInstructor 상태 변경 → FCM push + Notification 생성 ────────────
#   Notification 생성 후 (1)번 시그널이 자동으로 WS 브로드캐스트를 처리함.

_STATUS_MESSAGES = {
    PendingInstructor.Status.VERIFIED: {
        'body': '클래씨 강사로 승인되었습니다. 지금 로그인하여 활동을 시작해 보세요.',
    },
    PendingInstructor.Status.SUSPENDED: {
        'body': '제출하신 서류를 다시 확인해주세요. 자세한 문의는 고객센터를 이용해 주세요.',
    },
}

_STATUS_TITLES = {
    PendingInstructor.Status.VERIFIED: '{nickname}님의 강사 인증이 완료되었습니다! 🎉',
    PendingInstructor.Status.SUSPENDED: '{nickname}님의 강사 인증이 반려되었습니다.',
}


@receiver(post_save, sender=PendingInstructor)
def notify_instructor_status_change(sender, instance, created, **kwargs):
    """
    PendingInstructor.status 변경 시 FCM push + 인앱 Notification 생성.
    최초 생성(created=True)은 무시.
    """
    if created:
        return

    logger.info(f"*** [Signal] Instructor status change: {instance.instructor_profile.user.email} → {instance.status} ***")

    msg = _STATUS_MESSAGES.get(instance.status)
    if not msg:
        logger.debug(f"*** [Signal] No message defined for status: {instance.status} ***")
        return

    user = instance.instructor_profile.user
    nickname = user.user_name
    title = _STATUS_TITLES.get(instance.status, '클래씨 알림').format(nickname=nickname)

    # 1) FCM push
    from config.apps.notification.fcm import send_push_to_user
    send_push_to_user(
        user=user,
        title=title,
        body=msg['body'],
        data={'type': 'instructor_status', 'status': instance.status},
    )

    # 2) 인앱 Notification 생성 → (1)번 시그널이 자동으로 WS 브로드캐스트 처리
    from config.apps.notification.models import Notification
    Notification.objects.create(
        user=user,
        type='instructor_status',
        role='instructor',
        title=title,
        body=msg['body'],
        data={'status': instance.status},
    )

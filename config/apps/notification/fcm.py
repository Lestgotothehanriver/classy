"""
FCM(Firebase Cloud Messaging) 푸시 알림 전송 유틸.

사용 전 requirements에 firebase-admin 추가 필요:
    pip install firebase-admin

그리고 settings.py에 서비스 계정 JSON 경로 설정:
    FCM_CREDENTIALS_PATH = BASE_DIR / 'firebase-service-account.json'
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

_app_initialized = False


def _get_fcm_app():
    global _app_initialized
    if _app_initialized:
        return
    logger.info("*** [FCM] Initializing Firebase Admin SDK... ***")
    try:
        import os
        import json
        import firebase_admin
        from firebase_admin import credentials
        
        if not firebase_admin._apps:
            fcm_json_str = os.environ.get('FCM_CREDENTIALS_JSON')
            
            if fcm_json_str:
                logger.info("*** [FCM] Using credentials from environment variable (FCM_CREDENTIALS_JSON) ***")
                cred_dict = json.loads(fcm_json_str)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                logger.info("*** [FCM] Firebase Admin SDK initialized successfully ***")
            else:
                cred_path = os.environ.get('FCM_SA_PATH') or getattr(settings, 'FCM_CREDENTIALS_PATH', None)
                if cred_path:
                    logger.info(f"*** [FCM] Using credentials from: {cred_path} ***")
                    cred = credentials.Certificate(str(cred_path))
                    firebase_admin.initialize_app(cred)
                    logger.info("*** [FCM] Firebase Admin SDK initialized successfully ***")
                else:
                    logger.warning("*** [FCM] Both FCM_CREDENTIALS_JSON and FCM_SA_PATH missing ***")
        else:
            logger.info("*** [FCM] Firebase Admin SDK already initialized ***")
            
        _app_initialized = True
    except Exception as e:
        logger.error(f"*** [FCM] firebase-admin initialization failed: {e} ***")


def _build_fcm_message(token, platform, title, body, str_data):
    """
    단일 디바이스용 messaging.Message 를 구성한다.

    채팅 메시지(type='message')는 '방당 알림 1개 갱신 + 답장'을 위해 플랫폼별로 다르게 보낸다.
      - Android: data-only 로 보내 앱이 직접 렌더(tag/MessagingStyle/답장 액션).
                 notification 페이로드가 있으면 background에서 OS가 가로채므로 제거한다.
      - iOS: alert(notification) 유지 + apns-collapse-id(방당 합치기)/thread-id(그룹)/
             category='chat_reply'(답장 액션)를 실어 OS가 처리하게 한다.
    그 외 이벤트 알림(과외 요청/제안/수락/성사, 강사 승인 등)은 기존 동작을 그대로 유지한다.

    DB에 의존하지 않는 순수 함수라 단위 테스트가 가능하다.
    """
    from firebase_admin import messaging

    platform = (platform or 'android').lower()
    is_chat = str_data.get('type') == 'message'
    room_id = str_data.get('room_id')
    collapse_id = f"chat_{room_id}" if (is_chat and room_id) else 'status_update'

    # 채팅 알림 data: 클라가 알림을 직접 렌더/갱신할 수 있게 title/body 포함
    chat_data = {**str_data, 'title': title, 'body': body}

    # 채팅 + Android → data-only (앱이 직접 렌더)
    if is_chat and platform == 'android':
        return messaging.Message(
            data=chat_data,
            android=messaging.AndroidConfig(
                collapse_key=collapse_id,
                priority='high',
            ),
            token=token,
        )

    # 채팅 + iOS → alert 유지 + collapse/thread/category
    if is_chat and platform == 'ios':
        return messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=chat_data,
            apns=messaging.APNSConfig(
                headers={'apns-collapse-id': collapse_id},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        thread_id=collapse_id,
                        category='chat_reply',
                        mutable_content=True,
                    ),
                ),
            ),
            token=token,
        )

    # 비채팅(이벤트) 또는 알 수 없는 플랫폼 → 기존 동작 유지
    return messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=str_data,
        android=messaging.AndroidConfig(
            notification=messaging.AndroidNotification(
                channel_id='classy_high_importance_channel',
                priority='high',
            ),
            collapse_key=collapse_id,
            priority='high',
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound='default'),
            ),
        ),
        token=token,
    )


def send_push_to_user(user, title: str, body: str, data: dict = None):
    """
    특정 user의 활성화된 모든 DeviceToken에 FCM push 전송.
    firebase-admin 미설치 시 로그만 남기고 graceful 종료.
    """
    from .models import DeviceToken
    logger.info(f"*** [FCM] Request to send push to: {user.email} (Title: {title}) ***")
    
    token_rows = list(
        DeviceToken.objects
        .filter(user=user, is_active=True)
        .values_list('token', 'platform')
    )
    if not token_rows:
        logger.info(f"*** [FCM] No active tokens found for user: {user.email} ***")
        return

    str_data = {k: str(v) for k, v in (data or {}).items()}

    try:
        _get_fcm_app()
        from firebase_admin import messaging
        logger.debug(f"*** [FCM] Sending messages to {len(token_rows)} devices for {user.email}... ***")

        messages = [
            _build_fcm_message(token, platform, title, body, str_data)
            for token, platform in token_rows
        ]
        response = messaging.send_each(messages)
        logger.info(f"*** [FCM] Success: {response.success_count}, Failure: {response.failure_count} for {user.email} ***")
    except ImportError:
        logger.warning(f"*** [FCM] firebase-admin NOT INSTALLED. Skip push to {user.email} ***")
    except Exception as e:
        logger.error(f"*** [FCM] Error sending push to {user.email}: {e} ***")

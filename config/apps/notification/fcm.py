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
        import firebase_admin
        from firebase_admin import credentials
        cred_path = getattr(settings, 'FCM_CREDENTIALS_PATH', None)
        if cred_path and not firebase_admin._apps:
            logger.info(f"*** [FCM] Using credentials from: {cred_path} ***")
            cred = credentials.Certificate(str(cred_path))
            firebase_admin.initialize_app(cred)
            logger.info("*** [FCM] Firebase Admin SDK initialized successfully ***")
        else:
            logger.warning("*** [FCM] FCM_CREDENTIALS_PATH missing or app already exists ***")
        _app_initialized = True
    except Exception as e:
        logger.error(f"*** [FCM] firebase-admin initialization failed: {e} ***")


def send_push_to_user(user, title: str, body: str, data: dict = None):
    """
    특정 user의 활성화된 모든 DeviceToken에 FCM push 전송.
    firebase-admin 미설치 시 로그만 남기고 graceful 종료.
    """
    from .models import DeviceToken
    logger.info(f"*** [FCM] Request to send push to: {user.email} (Title: {title}) ***")
    
    tokens = list(
        DeviceToken.objects
        .filter(user=user, is_active=True)
        .values_list('token', flat=True)
    )
    if not tokens:
        logger.info(f"*** [FCM] No active tokens found for user: {user.email} ***")
        return

    try:
        _get_fcm_app()
        from firebase_admin import messaging
        logger.debug(f"*** [FCM] Sending messages to {len(tokens)} devices for {user.email}... ***")
        
        messages = [
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                # Android: 앱 종료 상태에서도 올바른 채널로 알림 표시
                android=messaging.AndroidConfig(
                    notification=messaging.AndroidNotification(
                        channel_id='classy_high_importance_channel',
                        priority='high',
                    ),
                    collapse_key='status_update',
                    priority='high',
                ),
                # iOS: 뱃지 + 사운드 기본 설정
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(sound='default'),
                    ),
                ),
                token=token,
            )
            for token in tokens
        ]
        response = messaging.send_each(messages)
        logger.info(f"*** [FCM] Success: {response.success_count}, Failure: {response.failure_count} for {user.email} ***")
    except ImportError:
        logger.warning(f"*** [FCM] firebase-admin NOT INSTALLED. Skip push to {user.email} ***")
    except Exception as e:
        logger.error(f"*** [FCM] Error sending push to {user.email}: {e} ***")

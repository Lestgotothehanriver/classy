import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeviceToken, Notification

logger = logging.getLogger(__name__)


class NotificationListAPIView(APIView):
    """
    URL: /notification/

    유저가 수신한 '알림(Notification)' 목록을 조회하거나 일괄 삭제하는 API View입니다.

    Response (GET /):
        HTTP 200 OK:
        [
            {
                "id": 1,
                "type": "NEW_PROPOSAL",
                "role": "student",
                "title": "과외 제안이 도착했습니다",
                "body": "홍길동 강사님이 제안을 보냈습니다.",
                "data": {"proposal_id": 123},
                "is_read": false,
                "created_at": "2026-04-26T06:51:26Z"
            }
        ]

    Endpoints:
        GET /notification/             : 본인의 전체 알림 조회.
        GET /notification/?role=student: 특정 역할의 알림만 필터링 조회.
        DELETE /notification/          : 읽은 알림 전체 삭제.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = request.query_params.get("role")
        logger.info(
            "*** [NotificationList] Fetch notifications for user: %s (Role Filter: %s) ***",
            request.user.email,
            role,
        )
        qs = Notification.objects.filter(user=request.user)
        if role in ("student", "instructor"):
            qs = qs.filter(role=role)
        data = [_serialize(n) for n in qs]
        return Response(data, status=200)

    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(
            user=request.user, is_read=True
        ).delete()
        _broadcast_unread_counts(request.user)
        return Response({"deleted": deleted_count}, status=200)


class NotificationUnreadCountAPIView(APIView):
    """
    URL: /notification/unread-count/

    본인의 '안 읽은 알림(is_read=False) 개수'를 역할별로 조회하는 API View입니다.

    앱 진입 시 뱃지(Badge) 업데이트를 위해 호출됩니다.
    이후의 갱신은 WebSocket(notification.counts)을 통해 실시간으로 처리됩니다.

    Endpoints:
        GET /notification/unread-count/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        base_qs = Notification.objects.filter(user=request.user, is_read=False)
        return Response(
            {
                "student": base_qs.filter(role="student").count(),
                "instructor": base_qs.filter(role="instructor").count(),
            },
            status=200,
        )


class NotificationReadAPIView(APIView):
    """
    URL: /notification/<pk>/read/

    특정 알림을 '읽음 처리(is_read=True)'하는 API View입니다.

    Response (PATCH /):
        HTTP 200 OK:
        {
            "id": 1,
            "type": "NEW_PROPOSAL",
            "role": "student",
            "title": "과외 제안이 도착했습니다",
            "body": "홍길동 강사님이 제안을 보냈습니다.",
            "data": {"proposal_id": 123},
            "is_read": true,
            "created_at": "2026-04-26T06:51:26Z"
        }

    Endpoints:
        PATCH /notification/<pk>/read/
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        logger.info(
            "*** [NotificationRead] Mark notification %s as read for: %s ***",
            pk,
            request.user.email,
        )
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            logger.warning(
                "*** [NotificationRead] Notification %s not found for user: %s ***",
                pk,
                request.user.email,
            )
            return Response({"error": "Not found"}, status=404)

        notification.is_read = True
        notification.save(update_fields=["is_read"])
        _broadcast_unread_counts(request.user)
        return Response(_serialize(notification), status=200)


class NotificationReadAllAPIView(APIView):
    """
    URL: /notification/read-all/

    본인이 수신한 '모든 안 읽은 알림'을 일괄적으로 '읽음 처리(is_read=True)'하는 API View입니다.

    알림 탭에서 "모두 읽음" 버튼을 클릭할 때 사용되며,
    처리 후 WebSocket 채널로 0으로 초기화된 카운트를 브로드캐스트합니다.

    Endpoints:
        PATCH /notification/read-all/
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        updated = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        _broadcast_unread_counts(request.user)
        return Response({"updated": updated}, status=200)


class DeviceTokenAPIView(APIView):
    """
    URL: /device-token/

    FCM(Firebase Cloud Messaging) 또는 APNs의 '디바이스 푸시 토큰(DeviceToken)'을 
    생성, 조회, 수정(알림 켜기/끄기)하는 API View입니다.

    앱 로그인 시 디바이스 토큰이 서버로 전송되어 `post` 엔드포인트를 통해 갱신되며,
    알림 설정(수신 거부/허용)은 `put` 엔드포인트를 통해 상태(is_active)를 토글합니다.
    다른 유저가 동일한 토큰을 사용할 경우, 해당 토큰은 이전 유저에게서 삭제되고 현재 유저에게 할당됩니다.

    Endpoints:
        GET /device-token/   : 현재 디바이스의 푸시 알림 활성화 여부 반환.
        POST /device-token/  : 새 푸시 토큰 등록 및 기기 플랫폼(OS) 업데이트.
        PUT /device-token/   : 푸시 알림 수신 동의 상태(is_active) 토글.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        token_obj = (
            DeviceToken.objects.filter(user=request.user)
            .order_by("-updated_at")
            .first()
        )
        if token_obj is None:
            return Response({"is_active": None, "is_chat_active": None}, status=200)
        return Response({
            "is_active": token_obj.is_active,
            "is_chat_active": token_obj.is_chat_active
        }, status=200)

    def post(self, request):
        fcm_token = request.data.get("token", "").strip()
        platform = request.data.get("platform", "android")
        explicit_state = request.data.get("is_active")
        explicit_chat_state = request.data.get("is_chat_active")
        logger.info(
            "*** [DeviceToken] Register attempt for user: %s (Platform: %s) ***",
            request.user.email,
            platform,
        )

        if not fcm_token:
            logger.warning(
                "*** [DeviceToken] Missing token in request from: %s ***",
                request.user.email,
            )
            return Response({"error": "token is required"}, status=400)

        deleted_count, _ = (
            DeviceToken.objects.filter(token=fcm_token)
            .exclude(user=request.user)
            .delete()
        )
        if deleted_count > 0:
            logger.info(
                "*** [DeviceToken] Removed old token mapping from %s other users ***",
                deleted_count,
            )

        obj, created = DeviceToken.objects.get_or_create(
            token=fcm_token,
            defaults={
                "user": request.user,
                "platform": platform,
                "is_active": _coerce_is_active(explicit_state, default=True),
                "is_chat_active": _coerce_is_active(explicit_chat_state, default=True),
            },
        )
        if not created:
            logger.info(
                "*** [DeviceToken] Updating existing token record for: %s ***",
                request.user.email,
            )
            obj.user = request.user
            obj.platform = platform
            update_fields = ["user", "platform", "updated_at"]
            if explicit_state is not None:
                obj.is_active = _coerce_is_active(explicit_state, default=obj.is_active)
                update_fields.append("is_active")
            if explicit_chat_state is not None:
                obj.is_chat_active = _coerce_is_active(explicit_chat_state, default=obj.is_chat_active)
                update_fields.append("is_chat_active")
            obj.save(update_fields=update_fields)
        else:
            logger.info(
                "*** [DeviceToken] New token record created for: %s ***",
                request.user.email,
            )

        return Response({
            "registered": True,
            "is_active": obj.is_active,
            "is_chat_active": obj.is_chat_active
        }, status=201)

    def put(self, request):
        qs = DeviceToken.objects.filter(user=request.user).order_by("-updated_at")
        if not qs.exists():
            return Response({"error": "No device token registered"}, status=404)

        token_obj = qs.first()
        
        has_is_active = "is_active" in request.data
        has_is_chat_active = "is_chat_active" in request.data
        update_fields = ["updated_at"]
        
        if has_is_chat_active:
            explicit_chat_state = request.data.get("is_chat_active")
            token_obj.is_chat_active = _coerce_is_active(
                explicit_chat_state,
                default=not token_obj.is_chat_active,
            )
            update_fields.append("is_chat_active")
            
        if has_is_active or not has_is_chat_active:
            explicit_state = request.data.get("is_active")
            token_obj.is_active = _coerce_is_active(
                explicit_state,
                default=not token_obj.is_active,
            )
            update_fields.append("is_active")
            
        token_obj.save(update_fields=update_fields)
        return Response({
            "is_active": token_obj.is_active,
            "is_chat_active": token_obj.is_chat_active
        }, status=200)


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "role": n.role,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat(),
    }


def _coerce_is_active(raw, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes", "on")
    return bool(raw)


def _broadcast_unread_counts(user) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    base_qs = Notification.objects.filter(user=user, is_read=False)
    async_to_sync(channel_layer.group_send)(
        f"notification_user_{user.id}",
        {
            "type": "notification.counts",
            "student": base_qs.filter(role="student").count(),
            "instructor": base_qs.filter(role="instructor").count(),
        },
    )

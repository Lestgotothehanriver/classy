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

    GET 요청 시, 본인이 수신한 전체 알림 목록을 최신순으로 반환하며 쿼리 파라미터를 통해 특정 역할군(student | instructor)의 알림만 필터링 조회할 수 있습니다.
    DELETE 요청 시, 로그인한 사용자의 알림 중 이미 읽음(is_read=True) 상태인 알림을 일괄 삭제합니다.

    Query Parameters:
        role (str, optional): 필터링할 역할 ('student' | 'instructor').

    Returns:
        Response (GET): List[dict] 데이터 (각 항목당 id, type, role, title, body, data, is_read, created_at 포함)
        Response (DELETE): {
            "deleted": int
        }
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

    GET 요청 시 앱 진입 또는 갱신을 위해 안 읽은 알림 수를 각각 student 및 instructor 역할별 카운트로 나누어 반환합니다.

    Returns:
        Response: {
            "student": int,
            "instructor": int
        }
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

    PATCH 요청 시, 지정한 알림의 읽음(is_read) 여부를 True로 갱신하고 변경 사항을 저장한 뒤 갱신된 알림의 상세 정보를 반환합니다.

    Path Parameters:
        pk (int): 읽음 처리할 알림 ID.

    Returns:
        Response: {
            "id": int,
            "type": str,
            "role": str,
            "title": str,
            "body": str,
            "data": dict,
            "is_read": True,
            "created_at": str (ISO datetime)
        }
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

    PATCH 요청 시 로그인한 사용자가 수신한 모든 읽지 않은 알림을 일괄적으로 읽음(is_read=True) 상태로 업데이트합니다.

    Returns:
        Response: {
            "updated": int
        }
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

    FCM(Firebase Cloud Messaging) 또는 APNs의 '디바이스 푸시 토큰(DeviceToken)'을 생성, 조회, 수정(알림 켜기/끄기)하는 API View입니다.

    GET 요청 시 로그인한 사용자의 최신 단말 토큰에 설정된 푸시 알림 수신 상태(is_active) 및 채팅 알림 수신 상태(is_chat_active)를 조회합니다.
    POST 요청 시 최신 FCM 토큰 정보와 플랫폼, 활성화 상태 정보를 등록받아 생성 및 업데이트를 완료합니다. 타 유저의 기기 이전으로 인한 중복 토큰이 있는 경우 삭제 처리합니다.
    PUT 요청 시 단말 토큰의 전체 알림 수신 여부(is_active) 또는 채팅 알림 수신 여부(is_chat_active)를 전달받은 상태로 수정하거나 명시적 파라미터가 없으면 반전(토글)합니다.

    Request Body (POST):
        token (str): FCM 디바이스 토큰 문자열 (필수).
        platform (str, optional): 디바이스 플랫폼 종류 ('android' | 'ios', 기본값 'android').
        is_active (bool, optional): 전체 알림 수신 동의 여부.
        is_chat_active (bool, optional): 채팅 알림 수신 동의 여부.

    Request Body (PUT):
        is_active (bool, optional): 전체 알림 수신 활성 상태 값.
        is_chat_active (bool, optional): 채팅 알림 수신 활성 상태 값.

    Returns:
        Response (GET): {
            "is_active": bool,
            "is_chat_active": bool
        }
        Response (POST): {
            "registered": True,
            "is_active": bool,
            "is_chat_active": bool
        } (HTTP 201 Created)
        Response (PUT): {
            "is_active": bool,
            "is_chat_active": bool
        }
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

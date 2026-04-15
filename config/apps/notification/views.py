from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Notification


class NotificationListAPIView(APIView):
    """
    GET  /notification/              — 내 전체 알림 목록 (최신순)
    GET  /notification/?role=student — role별 필터
    DELETE /notification/            — 읽은 알림 전체 삭제
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user)
        role = request.query_params.get("role")
        if role in ("student", "instructor"):
            qs = qs.filter(role=role)
        data = [_serialize(n) for n in qs]
        return Response(data, status=status.HTTP_200_OK)

    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(
            user=request.user, is_read=True
        ).delete()
        return Response({"deleted": deleted_count}, status=status.HTTP_200_OK)


class NotificationUnreadCountAPIView(APIView):
    """
    GET /notification/unread-count/              — role별 미읽음 카운트
    응답: { "student": 3, "instructor": 1 }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        base_qs = Notification.objects.filter(user=request.user, is_read=False)
        return Response({
            "student":    base_qs.filter(role="student").count(),
            "instructor": base_qs.filter(role="instructor").count(),
        }, status=status.HTTP_200_OK)

    
class NotificationReadAPIView(APIView):
    """
    PATCH /notification/<pk>/read/  — 개별 알림 읽음 처리
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(_serialize(notification), status=status.HTTP_200_OK)


class NotificationReadAllAPIView(APIView):
    """
    PATCH /notification/read-all/  — 전체 읽음 처리
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        updated = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        return Response({"updated": updated}, status=status.HTTP_200_OK)


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


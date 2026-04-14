from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework import serializers

from config.apps.chat_app.notifications import push_to_all
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "body", "data", "is_read", "created_at"]


class NotificationListView(APIView):
    """
    GET /notification/          — 내 알림 목록 (최신순)
    DELETE /notification/       — 읽은 알림 전체 삭제
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user)
        serializer = NotificationSerializer(qs, many=True)
        return Response(serializer.data)

    def delete(self, request):
        Notification.objects.filter(user=request.user, is_read=True).delete()
        return Response({"ok": True})


class NotificationReadView(APIView):
    """
    PATCH /notification/<pk>/read/  — 개별 알림 읽음 처리
    PATCH /notification/read-all/   — 전체 읽음 처리
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk=None):
        if pk:
            Notification.objects.filter(user=request.user, pk=pk).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"ok": True})


class AnnouncementPushView(APIView):
    """
    POST /notification/announce/
    {"title": "공지 제목", "body": "공지 내용"}
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        title = request.data.get("title", "").strip()
        body = request.data.get("body", "").strip()
        if not title or not body:
            return Response({"error": "title과 body는 필수입니다."}, status=400)

        result = push_to_all(title=title, body=body, data={"type": "announcement"})
        return Response(result)

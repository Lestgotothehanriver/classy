"""고객지원 전용 WebSocket 라우팅입니다."""

from django.urls import path

from .consumers import AdminSupportInboxConsumer, SupportConversationConsumer


websocket_urlpatterns = [
    path("ws/admin/support/inbox/", AdminSupportInboxConsumer.as_asgi()),
    path(
        "ws/support/conversations/<int:conversation_id>/",
        SupportConversationConsumer.as_asgi(),
    ),
]

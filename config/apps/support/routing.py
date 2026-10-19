"""고객지원 전용 WebSocket 라우팅입니다."""

from django.urls import path

from .consumers import SupportConversationConsumer


websocket_urlpatterns = [
    path(
        "ws/support/conversations/<int:conversation_id>/",
        SupportConversationConsumer.as_asgi(),
    ),
]

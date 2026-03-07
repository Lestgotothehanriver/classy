from django.urls import path, re_path
from .consumers import ChatConsumer
print("✅ [Routing] WebSocket URL patterns loaded")
websocket_urlpatterns = [
    path("ws/chat/<int:room_id>/", ChatConsumer.as_asgi()),
]
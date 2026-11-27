from django.urls import path, re_path
from .consumers import ChatConsumer

websocket_urlpatterns = [
    path("ws/chat/public/<uuid:public_id>/", ChatConsumer.as_asgi()),
    path("ws/chat/<int:room_id>/", ChatConsumer.as_asgi()),
]

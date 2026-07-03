from rest_framework.routers import DefaultRouter
from .views import ChatRoomViewSet, ImageUploadView, DeviceTokenView, ChatNotificationToggleView
from django.urls import path

router = DefaultRouter()
router.register("chatrooms", ChatRoomViewSet, basename="chatroom")

urlpatterns = [
    path("images/", ImageUploadView.as_view(), name="image-upload"),
    path("device-token/", DeviceTokenView.as_view(), name="device-token"),
    path("chat-notification/", ChatNotificationToggleView.as_view(), name="chat-notification"),
] + router.urls


from django.urls import path
from .views import (
    NotificationListAPIView,
    NotificationUnreadCountAPIView,
    NotificationReadAPIView,
    NotificationReadAllAPIView,
    DeviceTokenAPIView,
)

urlpatterns = [
    path('', NotificationListAPIView.as_view()),
    path('unread-count/', NotificationUnreadCountAPIView.as_view()),
    path('read-all/', NotificationReadAllAPIView.as_view()),
    path('<int:pk>/read/', NotificationReadAPIView.as_view()),
]

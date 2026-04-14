from django.urls import path
from .views import NotificationListView, NotificationReadView, AnnouncementPushView
from .admin import AdminAnnouncementView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path("<int:pk>/read/", NotificationReadView.as_view(), name="notification-read"),
    path("read-all/", NotificationReadView.as_view(), name="notification-read-all"),
    path("announce/", AnnouncementPushView.as_view(), name="announce"),
    path("admin/announce/", AdminAnnouncementView.as_view(), name="admin-announce"),
]

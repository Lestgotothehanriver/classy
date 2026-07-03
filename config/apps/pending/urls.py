from django.urls import path
from .views import PendingUploadView, PendingCreateAPIView

app_name = "pending"

urlpatterns = [
    path("", PendingCreateAPIView.as_view(), name="pending-create"),
    path("upload/", PendingUploadView.as_view(), name="pending-upload"),
]
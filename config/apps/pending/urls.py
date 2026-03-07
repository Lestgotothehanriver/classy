from django.urls import path
from .views import PendingUploadView

app_name = "pending"

urlpatterns = [
    path("upload/", PendingUploadView.as_view(), name="pending-upload"),
]
from django.urls import path

from .views import ReportCreateAPIView

urlpatterns = [
    path("create/", ReportCreateAPIView.as_view(), name="report-create"),
]

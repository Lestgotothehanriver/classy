from django.urls import path

from .views import ReportCreateAPIView, InquiryCreateAPIView

urlpatterns = [
    path("create/", ReportCreateAPIView.as_view(), name="report-create"),
    path("inquiry/", InquiryCreateAPIView.as_view(), name="inquiry-create"),
]

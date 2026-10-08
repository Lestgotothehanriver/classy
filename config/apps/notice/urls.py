from django.urls import path

from .views import NoticeDetailView, NoticeExposureView, NoticeListView

app_name = "notice"

urlpatterns = [
    path("", NoticeListView.as_view(), name="list"),
    path("exposure/", NoticeExposureView.as_view(), name="exposure"),
    path("<int:pk>/", NoticeDetailView.as_view(), name="detail"),
]

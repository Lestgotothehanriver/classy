from django.urls import path

from .views import NoticeDetailView, NoticeExposureView, NoticeListView, NoticePublicDetailView

app_name = "notice"

urlpatterns = [
    path("", NoticeListView.as_view(), name="list"),
    path("exposure/", NoticeExposureView.as_view(), name="exposure"),
    path("public/<uuid:public_id>/", NoticePublicDetailView.as_view(), name="public-detail"),
    path("<int:pk>/", NoticeDetailView.as_view(), name="detail"),
]

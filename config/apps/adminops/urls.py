from django.urls import path

from .views import AdminLoginAPIView, AdminMeAPIView

app_name = "adminops"

urlpatterns = [
    path("auth/login/", AdminLoginAPIView.as_view(), name="admin-login"),
    path("auth/me/", AdminMeAPIView.as_view(), name="admin-me"),
]

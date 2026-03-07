# config/apps/accounts/urls.py

from django.urls import path
from .views import StudentSignupAPIView, InstructorSignupAPIView, LoginAPIView

app_name = "accounts"

urlpatterns = [
    path("signup/student/", StudentSignupAPIView.as_view(), name="signup-student"),
    path("signup/instructor/", InstructorSignupAPIView.as_view(), name="signup-instructor"),
    path("login/", LoginAPIView.as_view(), name="login"),
]

# config/apps/accounts/urls.py

from django.urls import path
from .views import StudentSignupAPIView, InstructorSignupAPIView, LoginAPIView, CheckUsernameAPIView

app_name = "accounts"

urlpatterns = [
    path("signup/student/", StudentSignupAPIView.as_view(), name="signup-student"),
    path("signup/instructor/", InstructorSignupAPIView.as_view(), name="signup-instructor"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("check-username/", CheckUsernameAPIView.as_view(), name="check-username"),  # 닉네임 중복 체크용 엔드포인트
]

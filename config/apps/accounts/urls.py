# config/apps/accounts/urls.py

from django.urls import path
from .views import StudentSignupAPIView, InstructorSignupAPIView, LoginAPIView, CheckUsernameAPIView, LogoutAPIView, WithdrawAPIView
from .views import UserProfileAPIView, ProfileImageAPIView

app_name = "accounts"

urlpatterns = [
    path("signup/student/", StudentSignupAPIView.as_view(), name="signup-student"), # 학생 회원가입 엔드포인트
    path("signup/instructor/", InstructorSignupAPIView.as_view(), name="signup-instructor"), # 강사 회원가입 엔드포인트
    path("login/", LoginAPIView.as_view(), name="login"), # 로그인 엔드포인트
    path("check-username/", CheckUsernameAPIView.as_view(), name="check-username"),  # 닉네임 중복 체크용 엔드포인트
    path("logout/", LogoutAPIView.as_view(), name="logout"),  # 로그아웃 엔드포인트
    path("withdraw/", WithdrawAPIView.as_view(), name="withdraw"),  # 회원 탈퇴 엔드포인트
    path("me/", UserProfileAPIView.as_view(), name="user-profile"),              # 유저 정보 조회 및 수정 엔드포인트
    path("me/image/", ProfileImageAPIView.as_view(), name="user-profile-image"), # 유저 프로필 이미지 수정 엔드포인트
]

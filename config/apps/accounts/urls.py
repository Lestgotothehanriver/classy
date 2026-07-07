# config/apps/accounts/urls.py

from django.urls import path
from .views import (
    StudentSignupAPIView, InstructorSignupAPIView,
    LoginAPIView, CheckUsernameAPIView, CheckEmailAPIView,
    LogoutAPIView, WithdrawAPIView,
    InstructorRetryAPIView,
    UserProfileAPIView, ProfileImageAPIView,
    CheckPhoneAPIView, AddRoleAPIView,
    RequestPhoneChangeAPIView, VerifyPhoneChangeAPIView,
    UserDetailAPIView,
    SubjectListAPIView,
    SendAuthSMSAPIView, VerifyAuthSMSAPIView,
)

app_name = "accounts"

urlpatterns = [
    path("signup/student/", StudentSignupAPIView.as_view(), name="signup-student"),
    path("signup/instructor/", InstructorSignupAPIView.as_view(), name="signup-instructor"),
    path("signup/instructor/retry/", InstructorRetryAPIView.as_view(), name="retry-instructor"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("check-username/", CheckUsernameAPIView.as_view(), name="check-username"),
    path("check-email/", CheckEmailAPIView.as_view(), name="check-email"),
    path("check-phone/", CheckPhoneAPIView.as_view(), name="check-phone"),   # 신규
    path("add-role/", AddRoleAPIView.as_view(), name="add-role"),             # 신규
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("withdraw/", WithdrawAPIView.as_view(), name="withdraw"),
    path("me/", UserProfileAPIView.as_view(), name="user-profile"),
    path("me/image/", ProfileImageAPIView.as_view(), name="user-profile-image"),
    path("me/phone/request/", RequestPhoneChangeAPIView.as_view(), name="phone-change-request"),
    path("me/phone/verify/", VerifyPhoneChangeAPIView.as_view(), name="phone-change-verify"),
    path("user/<int:pk>/", UserDetailAPIView.as_view(), name="user-detail"),
    path("subjects/", SubjectListAPIView.as_view(), name="subject-list"),
    path("send-auth-sms/", SendAuthSMSAPIView.as_view(), name="send-auth-sms"),
    path("verify-auth-sms/", VerifyAuthSMSAPIView.as_view(), name="verify-auth-sms"),
]

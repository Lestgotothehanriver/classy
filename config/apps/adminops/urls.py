from django.urls import path

from .views import (
    AdminLoginAPIView,
    AdminMeAPIView,
    InstructorVerificationApproveView,
    InstructorVerificationDetailView,
    InstructorVerificationDocumentView,
    InstructorVerificationListView,
    InstructorVerificationRejectView,
    InstructorVerificationSummaryView,
    SettlementCancelView,
    SettlementCompleteView,
    SettlementDetailView,
    SettlementListView,
    SettlementSummaryView,
)

app_name = "adminops"

urlpatterns = [
    path("auth/login/", AdminLoginAPIView.as_view(), name="admin-login"),
    path("auth/me/", AdminMeAPIView.as_view(), name="admin-me"),
    # 학력 인증 관리
    path(
        "instructor-verifications/",
        InstructorVerificationListView.as_view(),
        name="instructor-verification-list",
    ),
    path(
        "instructor-verifications/summary/",
        InstructorVerificationSummaryView.as_view(),
        name="instructor-verification-summary",
    ),
    path(
        "instructor-verifications/<int:pk>/",
        InstructorVerificationDetailView.as_view(),
        name="instructor-verification-detail",
    ),
    path(
        "instructor-verifications/<int:pk>/approve/",
        InstructorVerificationApproveView.as_view(),
        name="instructor-verification-approve",
    ),
    path(
        "instructor-verifications/<int:pk>/reject/",
        InstructorVerificationRejectView.as_view(),
        name="instructor-verification-reject",
    ),
    path(
        "instructor-verifications/<int:pk>/documents/<int:file_id>/",
        InstructorVerificationDocumentView.as_view(),
        name="instructor-verification-document",
    ),
    # 정산 관리
    path(
        "settlements/",
        SettlementListView.as_view(),
        name="settlement-list",
    ),
    path(
        "settlements/summary/",
        SettlementSummaryView.as_view(),
        name="settlement-summary",
    ),
    path(
        "settlements/<int:pk>/",
        SettlementDetailView.as_view(),
        name="settlement-detail",
    ),
    path(
        "settlements/<int:pk>/complete/",
        SettlementCompleteView.as_view(),
        name="settlement-complete",
    ),
    path(
        "settlements/<int:pk>/cancel/",
        SettlementCancelView.as_view(),
        name="settlement-cancel",
    ),
]

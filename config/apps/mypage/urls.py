from django.urls import path
from .views import (
    StudentRentedLectureListView, StudentLikedLectureListView,
    InstructorUploadedLectureListView, InstructorSettlementRequestView, InstructorSettlementInfoView
)

urlpatterns = [
    path("student/rented-lectures/", StudentRentedLectureListView.as_view(), name="student-rented-lectures"),
    path("student/liked-lectures/", StudentLikedLectureListView.as_view(), name="student-liked-lectures"),
    path("instructor/uploaded-lectures/", InstructorUploadedLectureListView.as_view(), name="instructor-uploaded-lectures"),
    path("instructor/request-settlement/", InstructorSettlementRequestView.as_view(), name="instructor-request-settlement"),
    path("instructor/settlement-info/", InstructorSettlementInfoView.as_view(), name="instructor-settlement-info"),
]

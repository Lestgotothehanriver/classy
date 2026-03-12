from django.urls import path
from .views import (
    StudentMainAPIView, InstructorMainAPIView
)

urlpatterns = [
    path("student/", StudentMainAPIView.as_view(), name="student-main"),
    path("instructor/", InstructorMainAPIView.as_view(), name="instructor-main"),
]

from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (
    # ── 읽기(기존) ──────────────────────────────────
    InstructorListAPIView,
    InstructorInfoAPIView,
    InstructorReviewListAPIView,
    TutoringPostListAPIView,
    TutoringPostDetailAPIView,
    StudentReviewListAPIView,

    # ── 과외 매칭 및 제안 ───────────────────────────
    StudentProposeToInstructorAPIView,
    InstructorProposeToStudentAPIView,
    TutoringProposalViewSet,

    # ── CDP ViewSets ─────────────────────────────────
    InstructorInfoViewSet,
    InstructorReviewViewSet,
    TutoringPostViewSet,
    StudentReviewViewSet,
    TutoringResourceViewSet,
)

router = SimpleRouter()

# POST   /tutoring/instructor-info/
# PATCH  /tutoring/instructor-info/<pk>/
# DELETE /tutoring/instructor-info/<pk>/
router.register(r"instructor-info", InstructorInfoViewSet, basename="instructor-info")

# POST   /tutoring/reviews/instructor/
# PATCH  /tutoring/reviews/instructor/<pk>/
# DELETE /tutoring/reviews/instructor/<pk>/
router.register(r"reviews/instructor", InstructorReviewViewSet, basename="instructor-review")

# POST   /tutoring/posts/write/
# PATCH  /tutoring/posts/write/<pk>/
# DELETE /tutoring/posts/write/<pk>/
router.register(r"posts/write", TutoringPostViewSet, basename="tutoringpost-write")

# POST   /tutoring/reviews/student/
# PATCH  /tutoring/reviews/student/<pk>/
# DELETE /tutoring/reviews/student/<pk>/
router.register(r"reviews/student", StudentReviewViewSet, basename="student-review")

# GET, POST, PATCH, DELETE /tutoring/proposals/
router.register(r"proposals", TutoringProposalViewSet, basename="tutoring-proposal")

# GET, POST, PATCH, DELETE /tutoring/resources/
router.register(r"resources", TutoringResourceViewSet, basename="tutoring-resource")


urlpatterns = [
    # ____________________________________________________________________________________
    # 학생 페이지: 강사 탐색 (읽기)
    # ____________________________________________________________________________________
    path("instructors/", InstructorListAPIView.as_view(), name="instructor-list"),
    path("instructors/<int:instructor_id>/info/", InstructorInfoAPIView.as_view(), name="instructor-info-read"),
    path("instructors/<int:instructor_id>/reviews/", InstructorReviewListAPIView.as_view(), name="instructor-reviews"),

    # ____________________________________________________________________________________
    # 강사 페이지: 공고 탐색 (읽기)
    # ____________________________________________________________________________________
    path("posts/", TutoringPostListAPIView.as_view(), name="tutoringpost-list"),
    path("posts/<int:pk>/", TutoringPostDetailAPIView.as_view(), name="tutoringpost-detail"),
    path("students/<int:student_id>/reviews/", StudentReviewListAPIView.as_view(), name="student-reviews"),

    # ____________________________________________________________________________________
    # 과외 매칭 및 제안 생성
    # ____________________________________________________________________________________
    path("propose-to-instructor/", StudentProposeToInstructorAPIView.as_view(), name="propose-to-instructor"),
    path("propose-to-student/", InstructorProposeToStudentAPIView.as_view(), name="propose-to-student"),

    # ── ViewSet URLs (CDP) ───────────────────────────
    path("", include(router.urls)),
]

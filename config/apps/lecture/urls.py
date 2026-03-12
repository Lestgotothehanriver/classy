from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (
    LectureViewSet,
    LectureListAPIView,
    LectureStreamAPIView,
    LectureDetailAPIView,
    CommentListCreateAPIView,
    CommentUpdateDeleteAPIView,
    SearchHistoryCreateAPIView,
    SearchHistoryDeleteAPIView,
    LectureLikeAPIView,
)


router = SimpleRouter()

# POST   /lectures/write/
# PATCH  /lectures/write/<pk>/
# DELETE /lectures/write/<pk>/
router.register(r"write", LectureViewSet, basename="lecture-write")

urlpatterns = [
    # ── 강의 목록 (필터링) ────────────────────────────────────
    path("", LectureListAPIView.as_view(), name="lecture-list"),

    # ── 강의 상세 ──────────────────────────────────────────────
    path("<int:pk>/", LectureDetailAPIView.as_view(), name="lecture-detail"),

    # ── 강의 스트리밍 ──────────────────────────────────────────
    path("<int:pk>/stream/", LectureStreamAPIView.as_view(), name="lecture-stream"),

    # ── 강의 좋아요 ──────────────────────────────────────────
    path("<int:pk>/like/", LectureLikeAPIView.as_view(), name="lecture-like"),


    # ── 댓글 목록 + 작성 ─────────────────────────────────────
    path("<int:lecture_id>/comments/", CommentListCreateAPIView.as_view(), name="comment-list-create"),

    # ── 댓글 수정 + 삭제 ─────────────────────────────────────
    path("comments/<int:pk>/", CommentUpdateDeleteAPIView.as_view(), name="comment-update-delete"),

    # ── 검색 기록 생성 + 삭제 ─────────────────────────────────────
    path("search-history/", SearchHistoryCreateAPIView.as_view(), name="search-history-create"),
    path("search-history/<int:pk>/", SearchHistoryDeleteAPIView.as_view(), name="search-history-delete"),

    # ── ViewSet URLs (write) ─────────────────────────────────
    path("", include(router.urls)),
]

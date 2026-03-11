from rest_framework import generics, mixins, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from django.db.models import Count, F
from django.shortcuts import get_object_or_404

from config.apps.accounts.models import Instructor
from .models import Lecture, Comment
from .serializers import (
    LectureListSerializer,
    LectureDetailSerializer,
    LecturePreviewSerializer,
    LectureRecommendSerializer,
    LectureStreamSerializer,
    LectureWriteSerializer,
    CommentSerializer,
    CommentWriteSerializer,
)


# ────────────────────────────────────────────────────────────────────
# 유틸: 콤마 구분 문자열 → int 리스트
# ────────────────────────────────────────────────────────────────────
def parse_int_list(value):
    if not value:
        return []
    return [int(x) for x in value.split(",") if x.strip().isdigit()]


# ════════════════════════════════════════════════════════════════════
# 1) Lecture Create / Patch / Delete
# ════════════════════════════════════════════════════════════════════

class LectureViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """
    POST   /lectures/write/          강의 생성 (강사만)
    PATCH  /lectures/write/<pk>/     강의 수정 (본인만)
    DELETE /lectures/write/<pk>/     강의 삭제 (본인만)

    Request (POST / PATCH, multipart/form-data):
    {
        "video": <file>,
        "thumbnail": <file>,
        "title": "미적분 강의",
        "subjects": [36, 37],
        "price": 5000,
        "is_preview": false
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LectureWriteSerializer

    def get_queryset(self):
        return Lecture.objects.filter(instructor__user=self.request.user)

    def perform_create(self, serializer):
        instructor = get_object_or_404(Instructor, user=self.request.user)
        serializer.save(instructor=instructor)


# ════════════════════════════════════════════════════════════════════
# 2) Lecture Filtering & List
# ════════════════════════════════════════════════════════════════════

class LectureListAPIView(generics.ListAPIView):
    """
    GET /lectures/

    Query Params (선택):
    - subject=1,2,3        과목 필터
    - max_price=5000       가격 이하 필터
    - is_tutoring=true     강사 과외 모집 여부
    - region=서울           강사 지역 필터 (User.region)
    - university=UNIST     강사 학교 필터
    - department=컴퓨터공학   강사 학과 필터
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = LectureListSerializer

    def get_queryset(self):
        qs = Lecture.objects.select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects").annotate(
            like_count=Count("likes", distinct=True),
        ).order_by("-created_at")

        # 1) 과목 필터
        subject_ids = parse_int_list(self.request.query_params.get("subject"))
        if subject_ids:
            qs = qs.filter(subjects__number__in=subject_ids).distinct()

        # 2) 가격 필터
        max_price = self.request.query_params.get("max_price")
        if max_price and max_price.isdigit():
            qs = qs.filter(price__lte=int(max_price))

        # 3) 강사 과외 모집 여부 필터
        is_tutoring = self.request.query_params.get("is_tutoring")
        if is_tutoring is not None:
            qs = qs.filter(instructor__is_tutoring=is_tutoring.lower() in ("true", "1"))

        # 4) 강사 지역 필터
        region = self.request.query_params.get("region")
        if region:
            qs = qs.filter(instructor__user__region__icontains=region)

        # 5) 강사 학교 필터
        university = self.request.query_params.get("university")
        if university:
            qs = qs.filter(instructor__university__icontains=university)

        # 6) 강사 학과 필터
        department = self.request.query_params.get("department")
        if department:
            qs = qs.filter(instructor__department__icontains=department)

        return qs


# ════════════════════════════════════════════════════════════════════
# 3) Lecture Streaming View
# ════════════════════════════════════════════════════════════════════

class LectureStreamAPIView(generics.RetrieveAPIView):
    """
    GET /lectures/<pk>/stream/

    강의 스트리밍 뷰 — 영상 URL 반환 + 조회수 증가.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = LectureStreamSerializer
    queryset = Lecture.objects.all()

    def retrieve(self, request, *args, **kwargs):
        # 조회수 atomic 증가
        Lecture.objects.filter(pk=kwargs["pk"]).update(view_count=F("view_count") + 1)
        return super().retrieve(request, *args, **kwargs)


# ════════════════════════════════════════════════════════════════════
# 4) Lecture Detail View (영상 정보 + 프리뷰 + 추천 강의)
# ════════════════════════════════════════════════════════════════════

class LectureDetailAPIView(APIView):
    """
    GET /lectures/<pk>/

    반환 데이터:
      1) lecture_info   — 현재 강의의 모든 필드
      2) preview_video  — 같은 강사의 is_preview=True 강의
      3) recommended    — 같은 과목을 공유하는 강의 중 추천순 상위 10개 (video 제외)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        lecture = get_object_or_404(
            Lecture.objects.select_related("instructor", "instructor__user")
            .prefetch_related("subjects"),
            pk=pk,
        )

        # 조회수 atomic 증가
        Lecture.objects.filter(pk=pk).update(view_count=F("view_count") + 1)

        # (1) 현재 강의 정보
        lecture_data = LectureDetailSerializer(lecture).data

        # (2) 프리뷰 강의 — 같은 강사의 is_preview=True 영상
        preview = Lecture.objects.filter(
            instructor=lecture.instructor, is_preview=True
        ).exclude(pk=pk).first()
        preview_data = LecturePreviewSerializer(preview).data if preview else None

        # (3) 추천 강의 — 같은 과목을 공유하는 강의, 추천순(조회수+좋아요) 상위 10
        subject_ids = list(lecture.subjects.values_list("id", flat=True))
        recommended_qs = (
            Lecture.objects.filter(subjects__id__in=subject_ids)
            .exclude(pk=pk)
            .distinct()
            .annotate(like_count=Count("likes", distinct=True))
            .order_by("-like_count", "-view_count", "-created_at")[:10]
        )
        recommended_data = LectureRecommendSerializer(recommended_qs, many=True).data

        return Response({
            "lecture_info": lecture_data,
            "preview_video": preview_data,
            "recommended": recommended_data,
        })


# ════════════════════════════════════════════════════════════════════
# 5) Comment Views (Create / List / Patch / Delete)
# ════════════════════════════════════════════════════════════════════

class CommentListCreateAPIView(generics.ListCreateAPIView):
    """
    GET  /lectures/<lecture_id>/comments/   특정 강의 댓글 목록 (최상위만, replies 중첩)
    POST /lectures/<lecture_id>/comments/   댓글 작성
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CommentWriteSerializer
        return CommentSerializer

    def get_queryset(self):
        lecture_id = self.kwargs["lecture_id"]
        return (
            Comment.objects.filter(lecture_id=lecture_id, parent__isnull=True)
            .select_related("author", "referenced_person")
            .prefetch_related("replies", "replies__author", "replies__referenced_person")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        lecture = get_object_or_404(Lecture, pk=self.kwargs["lecture_id"])
        serializer.save(author=self.request.user, lecture=lecture)

    def create(self, request, *args, **kwargs):
        # lecture 필드를 URL에서 자동 할당하므로, request.data에 lecture가 없어도 처리
        data = request.data.copy()
        data["lecture"] = self.kwargs["lecture_id"]
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # 저장된 객체를 읽기 Serializer로 반환
        output = CommentSerializer(serializer.instance).data
        return Response(output, status=status.HTTP_201_CREATED)


class CommentUpdateDeleteAPIView(generics.UpdateAPIView, generics.DestroyAPIView):
    """
    PATCH  /lectures/comments/<pk>/   댓글 수정 (작성자만)
    DELETE /lectures/comments/<pk>/   댓글 삭제 (작성자만)
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CommentWriteSerializer

    def get_queryset(self):
        return Comment.objects.filter(author=self.request.user)

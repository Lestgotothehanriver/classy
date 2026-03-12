from rest_framework import generics, mixins, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from django.db.models import Count, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from config.apps.accounts.models import Instructor
from config.apps.cash.models import LectureRentalHistory
from .models import Lecture, Comment, SearchHistory
from .serializers import (
    LectureListSerializer,
    LectureDetailSerializer,
    LecturePreviewSerializer,
    LectureRecommendSerializer,
    LectureStreamSerializer,
    LectureWriteSerializer,
    CommentSerializer,
    CommentWriteSerializer,
    SearchHistorySerializer,
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

    Path Params: 
    - pk: lecture id

    Request (POST / PATCH, multipart/form-data):
    {
        "video": <file>,
        "thumbnail": <file>,
        "title": "미적분 강의",
        "subjects": [1, 2],
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
        
        # 새로 업로드하는 강의가 프리뷰 영상인 경우, 기존 프리뷰 영상 삭제
        is_preview = serializer.validated_data.get('is_preview', False)
        if is_preview:
            Lecture.objects.filter(instructor=instructor, is_preview=True).delete()
            
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
        from django.db.models import Exists, OuterRef, Value, BooleanField
        from config.apps.accounts.models import Student

        qs = Lecture.objects.select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects").annotate(
            like_count=Count("likes", distinct=True),
        ).order_by("-created_at")

        student = None
        if self.request.user.is_authenticated:
            student = Student.objects.filter(user=self.request.user).first()
        
        if student:
            qs = qs.annotate(
                is_liked=Exists(
                    Lecture.likes.through.objects.filter(
                        lecture_id=OuterRef("pk"),
                        student_id=student.pk
                    )
                )
            )
        else:
            qs = qs.annotate(is_liked=Value(False, output_field=BooleanField()))

        liked = self.request.query_params.get("liked")
        if liked is not None:
            qs = qs.filter(is_liked=(liked.lower() in ("true", "1")))

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

    Path Params:
    - pk: lecture id

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
        from django.db.models import Exists, OuterRef, Value, BooleanField
        from config.apps.accounts.models import Student

        student = None
        if request.user.is_authenticated:
            student = Student.objects.filter(user=request.user).first()

        qs = Lecture.objects.select_related("instructor", "instructor__user").prefetch_related("subjects")

        if student:
            qs = qs.annotate(
                is_liked=Exists(
                    Lecture.likes.through.objects.filter(
                        lecture_id=OuterRef("pk"),
                        student_id=student.pk
                    )
                )
            )
        else:
            qs = qs.annotate(is_liked=Value(False, output_field=BooleanField()))

        lecture = get_object_or_404(qs, pk=pk)

        # 조회수 atomic 증가
        Lecture.objects.filter(pk=pk).update(view_count=F("view_count") + 1)

        # ── 렌탈 상태 확인 로직 추가 ──
        rental_status = "none"
        if student:
            rentals = LectureRentalHistory.objects.filter(
                lecture=lecture,
                student=request.user
            ).order_by('-created_at')

            if rentals.exists():
                now = timezone.now()
                # 하나라도 유효한 렌탈이 있으면 valid
                is_valid = False
                for rental in rentals:
                    if not rental.is_canceled:
                        expiration_date = rental.created_at + timedelta(days=lecture.rental_period)
                        if expiration_date >= now:
                            is_valid = True
                            break
                
                if is_valid:
                    rental_status = "valid"
                else:
                    # 모든 렌탈이 취소되었거나 기간이 지났으면 expired
                    # (단, 취소된 것만 있다면 엄밀히 따져야 하나 요구사항 상 보통 이전에 대여한 기록이 있으므로)
                    # 취소 안된 만료된 기록이 있는지 확인
                    has_expired = False
                    for rental in rentals:
                        if not rental.is_canceled:
                            has_expired = True
                            break
                    
                    if has_expired:
                        rental_status = "expired"

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
            "rental_status": rental_status,
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

    Path Params:
    - lecture id

    Request (POST, 댓글):
    {
        "content": "정말 유익한 강의네요!",
        "parent": null,
        "referenced_person": null
    }

    Request (POST, 대댓글):
    {
        "content": "저도 동의합니다!",
        "parent": 1,
        "referenced_person": 5
    }
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

    Path Params:
    - pk: comment id

    Request (PATCH):
    {
        "content": "수정된 댓글 내용입니다."
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CommentWriteSerializer

    def get_queryset(self):
        return Comment.objects.filter(author=self.request.user)


# ════════════════════════════════════════════════════════════════════
# 6) Search History Views (Create / Delete)
# ════════════════════════════════════════════════════════════════════

MAX_SEARCH_HISTORY = 5  # 학생당 최대 검색 기록 수


class SearchHistoryCreateAPIView(generics.CreateAPIView):
    """
    POST /lectures/search-history/

    검색 기록 생성 — 인증된 학생의 검색 키워드를 저장한다.
    학생당 최대 5개까지 보관하며, 초과 시 가장 오래된 기록을 자동 삭제한다.

    Request:
    {
        "query": "미적분"
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SearchHistorySerializer

    def get_queryset(self):
        # 현재 인증된 학생의 검색 기록만 반환
        return SearchHistory.objects.filter(student=self.request.user.student_profile)

    def perform_create(self, serializer):
        student = self.request.user.student_profile
        # 검색 기록 저장 (student 자동 할당)
        serializer.save(student=student)

        # 최대 개수 초과 시 가장 오래된 기록 삭제
        qs = SearchHistory.objects.filter(student=student)
        if qs.count() > MAX_SEARCH_HISTORY:
            # ordering이 -created_at 이므로 .last()가 가장 오래된 기록
            oldest = qs.last()
            if oldest:
                oldest.delete()



class SearchHistoryDeleteAPIView(generics.DestroyAPIView):
    """
    DELETE /lectures/search-history/<pk>/

    검색 기록 삭제 — 본인의 검색 기록만 삭제할 수 있다.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SearchHistorySerializer

    def get_queryset(self):
        # 본인 소유 검색 기록만 조회 (다른 학생 기록 삭제 방지)
        return SearchHistory.objects.filter(student=self.request.user.student_profile)


# ════════════════════════════════════════════════════════════════════
# 7) Lecture Like View
# ════════════════════════════════════════════════════════════════════

class LectureLikeAPIView(APIView):
    """
    POST /lectures/<int:pk>/like/

    강의 좋아요 토글 — 인증된 학생만 가능.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from config.apps.accounts.models import Student
        
        lecture = get_object_or_404(Lecture, pk=pk)
        student = get_object_or_404(Student, user=request.user)

        if lecture.likes.filter(pk=student.pk).exists():
            lecture.likes.remove(student)
            is_liked = False
        else:
            lecture.likes.add(student)
            is_liked = True

        return Response({
            "is_liked": is_liked,
            "like_count": lecture.likes.count()
        }, status=status.HTTP_200_OK)

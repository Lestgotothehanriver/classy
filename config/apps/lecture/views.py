import logging
from rest_framework import generics, mixins, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from django.db import transaction
from django.db.models import Count, F, Q, Exists, OuterRef, Value, BooleanField
from django.shortcuts import get_object_or_404
from config.apps.block.utils import get_blocked_user_ids

from config.apps.accounts.models import Instructor, Student
from config.apps.common.permissions import IsVerifiedInstructor
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

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# 공통 유틸리티
# ════════════════════════════════════════════════════════════════════

def parse_int_list(value):
    """
    콤마로 구분된 문자열을 정수 리스트로 변환합니다.

    Args:
        value (str): "1,2,3" 형태의 문자열

    Returns:
        list[int]: 변환된 정수 리스트.
    """
    if not value:
        return []
    return [int(x) for x in value.split(",") if x.strip().isdigit()]


def parse_csv_list(value):
    """
    콤마로 구분된 문자열을 문자열 리스트로 변환합니다.

    Args:
        value (str): "a,b,c" 형태의 문자열

    Returns:
        list[str]: 공백이 제거된 문자열 리스트.
    """
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


VIDEO_LENGTH_RANGES = {
    "under_5": {"video_duration__gte": 1, "video_duration__lte": 5 * 60},
    "10_30": {"video_duration__gte": 10 * 60, "video_duration__lt": 30 * 60},
    "30_60": {"video_duration__gte": 30 * 60, "video_duration__lt": 60 * 60},
    "60_90": {"video_duration__gte": 60 * 60, "video_duration__lt": 90 * 60},
    "over_90": {"video_duration__gte": 90 * 60},
}


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
    URL: /lectures/write/
    URL: /lectures/write/<pk>/
    URL: /lectures/write/<pk>/stop-sales/

    강사가 자신의 VOD '강의(Lecture)'를 업로드하고 관리하는 API ViewSet입니다.

    Request (POST /):
        title (str): 강의 제목.
        content (str): 강의 설명.
        video (File): 강의 영상 파일 (S3 등 스토리지 업로드).
        thumbnail (File): 강의 썸네일 이미지.
        price (int): 강의 가격.
        is_preview (bool, optional): 프리뷰 영상 여부 (강사당 1개만 유지됨).

    Response (POST /):
        HTTP 201 Created:
        {
            "id": 1,
            "title": "강의 제목",
            "video_url": "...",
            "is_preview": false,
            "created_at": "2026-04-26T06:51:26Z"
        }
    """
    permission_classes = [permissions.IsAuthenticated, IsVerifiedInstructor]
    serializer_class = LectureWriteSerializer

    def get_queryset(self):
        # 본인(강사)이 업로드한 강의만 접근 가능 (삭제된 강의 제외)
        return Lecture.objects.filter(instructor__user=self.request.user, is_delete=False)

    def perform_create(self, serializer):
        """
        강의를 등록합니다.
        - is_preview=True인 경우: 기존에 등록된 프리뷰 영상을 먼저 삭제하고 새 것을 저장합니다.
          (강사 당 프리뷰 영상은 1개만 유지)
        - transaction.atomic()으로 삭제와 저장을 원자적으로 묶어,
          저장 실패 시 기존 프리뷰가 사라지는 데이터 손실을 방지합니다.
        """
        instructor = get_object_or_404(Instructor, user=self.request.user)
        is_preview = serializer.validated_data.get('is_preview', False)

        with transaction.atomic():
            if is_preview:
                # 기존 프리뷰 삭제와 새 강의 저장을 원자적으로 처리
                deleted_count, _ = Lecture.objects.filter(instructor=instructor, is_preview=True).delete()
                logger.info(
                    "[LECTURE] 기존 프리뷰 강의 삭제. instructor_id=%s, deleted=%d",
                    instructor.pk, deleted_count
                )
            serializer.save(instructor=instructor)
            logger.info(
                "[LECTURE] 강의 등록 완료. instructor_id=%s, lecture_id=%s, is_preview=%s",
                instructor.pk, serializer.instance.pk, is_preview
            )

    @action(detail=True, methods=['post'], url_path='stop-sales')
    def stop_sales(self, request, pk=None):
        """
        강의 판매를 중지합니다. (is_active=False로 변경)
        판매 중지된 강의는 목록에서 노출되지 않습니다.

        URL: POST /lectures/write/<pk>/stop-sales/
        """
        lecture = self.get_object()
        lecture.is_active = False
        lecture.save(update_fields=['is_active'])
        logger.info(
            "[LECTURE] 강의 판매 중지. instructor_id=%s, lecture_id=%s",
            request.user.pk, pk
        )
        return Response({"detail": "강의 판매가 중지되었습니다.", "is_active": False}, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════════════════
# 2) Lecture Filtering & List
# ════════════════════════════════════════════════════════════════════

class LectureListAPIView(generics.ListAPIView):
    """
    URL: /lectures/

    판매 중(is_active=True)인 전체 '강의 목록'을 조회하고 필터링하는 API View입니다.

    학생들이 강의를 검색할 수 있도록 다중 키워드, 지역, 가격, 길이 등 복합 필터링을 지원하며,
    학생 로그인 시 해당 강의의 찜(좋아요) 여부를 서브쿼리로 동적 계산하여 응답합니다.

    Query Parameters:
        q (str): 제목/과목/강사명 포괄 검색어.
        subject (str): 과목 ID (콤마 구분).
        max_price (str): 최대 가격 상한선.
        video_length (str): 영상 길이 범위 (예: 'under_5', '10_30').
        region, university, department, student_number: 강사 프로필 관련 필터.
        liked (bool): 본인이 찜한 강의만 조회할지 여부.

    Returns:
        List[LectureListSerializer]: 조건에 맞는 강의 목록.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LectureListSerializer

    def get_queryset(self):
        qs = Lecture.objects.filter(is_active=True, is_delete=False).select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects").annotate(
            like_count=Count("likes", distinct=True),
        ).order_by("-created_at")

        if self.request.user.is_authenticated:
            blocked_user_ids = get_blocked_user_ids(self.request.user)
            if blocked_user_ids:
                qs = qs.exclude(instructor__user_id__in=blocked_user_ids)

        student = Student.objects.filter(user=self.request.user).first() if self.request.user.is_authenticated else None
        
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

        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(subjects__name__icontains=q) |
                Q(instructor__user__user_name__icontains=q) |
                Q(instructor__university__icontains=q) |
                Q(instructor__department__icontains=q)
            ).distinct()

        subject_ids = parse_int_list(self.request.query_params.get("subject"))
        if subject_ids:
            qs = qs.filter(subjects__number__in=subject_ids).distinct()
        else:
            filter_types = parse_csv_list(self.request.query_params.get("filter_type"))
            if filter_types:
                filter_type_query = Q()
                for filter_type in filter_types:
                    filter_type_query |= Q(subjects__name__icontains=filter_type)
                qs = qs.filter(filter_type_query).distinct()

        max_price = self.request.query_params.get("max_price")
        if max_price and max_price.isdigit():
            qs = qs.filter(price__lte=int(max_price))
        video_length = self.request.query_params.get("video_length")
        if video_length in VIDEO_LENGTH_RANGES:
            qs = qs.filter(**VIDEO_LENGTH_RANGES[video_length])

        is_tutoring = self.request.query_params.get("is_tutoring")
        if is_tutoring is not None:
            qs = qs.filter(instructor__is_tutoring=is_tutoring.lower() in ("true", "1"))

        regions = parse_csv_list(self.request.query_params.get("region"))
        if regions:
            region_query = Q()
            for region in regions:
                region_query |= Q(instructor__user__region__icontains=region)
            qs = qs.filter(region_query)

        university = self.request.query_params.get("university")
        if university:
            qs = qs.filter(instructor__university__icontains=university)

        department = self.request.query_params.get("department")
        if department:
            qs = qs.filter(instructor__department__icontains=department)

        student_numbers = parse_csv_list(self.request.query_params.get("student_number"))
        if student_numbers:
            qs = qs.filter(instructor__student_number__in=student_numbers)

        instructor_param = self.request.query_params.get("instructor")
        if instructor_param:
            if instructor_param == "me" and self.request.user.is_authenticated:
                qs = qs.filter(instructor__user=self.request.user)
            elif instructor_param.isdigit():
                qs = qs.filter(instructor__id=int(instructor_param))

        return qs


# ════════════════════════════════════════════════════════════════════
# 3) Lecture Streaming View
# ════════════════════════════════════════════════════════════════════

class LectureStreamAPIView(generics.RetrieveAPIView):
    """
    URL: /lectures/<pk>/stream/

    유효한 대여 권한이 있는지 검증한 후, '강의 영상(Streaming URL)'을 반환하는 API View입니다.

    프리뷰 강의(is_preview=True)이거나 자신의 강의인 경우 권한 검증을 통과하며,
    그 외에는 LectureRentalHistory를 통해 결제 및 만료 여부를 체크합니다.

    Path Parameters:
        pk (int): 재생하려는 강의 ID.

    Returns:
        LectureStreamSerializer: 영상 URL 및 재생 관련 메타데이터.
        403 Forbidden: 대여 내역이 없거나 만료된 경우.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LectureStreamSerializer
    queryset = Lecture.objects.filter(is_delete=False)

    def retrieve(self, request, *args, **kwargs):
        """
        강의 영상 스트리밍 URL을 반환합니다.
        - is_preview=True인 경우: 누구나 무료로 시청 가능합니다.
        - is_preview=False인 경우: 유효한 대여 이력이 없으면 403 반환합니다.
          (대여 만료 여부는 Service Layer의 has_valid_rental에서 처리)
        """
        lecture = self.get_object()
        logger.debug(
            "[STREAM] 스트리밍 요청. user_id=%s, lecture_id=%s, is_preview=%s",
            request.user.pk, lecture.pk, lecture.is_preview
        )

        # 1. 프리뷰 강의이거나, 2. 본인의 강의인 경우 무료 패스
        if not lecture.is_preview and lecture.instructor.user != request.user:
            from .services import has_valid_rental
            if not has_valid_rental(request.user, lecture):
                logger.warning(
                    "[STREAM] 스트리밍 차단 — 유효한 대여 없음. user_id=%s, lecture_id=%s",
                    request.user.pk, lecture.pk
                )
                return Response(
                    {"error": "대여 후 시청할 수 있습니다."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        logger.info(
            "[STREAM] 스트리밍 허용. user_id=%s, lecture_id=%s",
            request.user.pk, lecture.pk
        )
        serializer = self.get_serializer(lecture)
        return Response(serializer.data)


# ════════════════════════════════════════════════════════════════════
# 4) Lecture Detail View
# ════════════════════════════════════════════════════════════════════

class LectureDetailAPIView(APIView):
    """
    URL: /lectures/<pk>/

    특정 강의의 '상세 페이지 데이터'를 한 번에 조립하여 반환하는 API View입니다.

    강의 기본 정보뿐만 아니라 현재 유저의 대여 상태, 강사의 무료 프리뷰 영상,
    그리고 연관 과목 기반의 추천 강의 10개를 한 응답으로 내려줍니다.
    호출 시 자동으로 강의 조회수(view_count)가 1 증가합니다.

    Path Parameters:
        pk (int): 상세 조회할 강의 ID.

    Returns:
        Response: {
            "lecture_info": LectureDetailSerializer 데이터,
            "rental_status": "none" | "valid" | "expired",
            "preview_video": LecturePreviewSerializer 데이터 (존재 시),
            "recommended": List[LectureRecommendSerializer]
        }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """
        강의 상세 페이지에 필요한 모든 데이터를 한 번에 반환합니다.
        - lecture_info: 강의 기본 정보 (제목, 가격, 강사 등)
        - rental_status: 현재 유저의 대여 상태 ("none" | "active" | "expired")
        - preview_video: 같은 강사의 무료 프리뷰 영상 (없으면 null)
        - recommended: 동일 과목 기반 추천 강의 목록 (최대 10개)
        """
        logger.debug("[LECTURE_DETAIL] 요청 시작. user_id=%s, lecture_pk=%s", request.user.pk, pk)

        student = None
        if request.user.is_authenticated:
            student = Student.objects.filter(user=request.user).first()

        # 삭제된 강의는 조회 불가 / 강의-강사-유저를 JOIN하여 N+1 방지
        qs = Lecture.objects.filter(is_delete=False).select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects")

        # 학생인 경우 해당 강의에 좋아요를 눌렀는지 여부를 서브쿼리로 한 번에 계산
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
            # 강사 계정이나 비인증 유저는 항상 is_liked=False
            qs = qs.annotate(is_liked=Value(False, output_field=BooleanField()))

        lecture = get_object_or_404(qs, pk=pk)

        # 조회수 원자적 증가 (F() expression으로 Race Condition 없이 DB 갱신)
        Lecture.objects.filter(pk=pk).update(view_count=F("view_count") + 1)
        lecture.view_count += 1  # 메모리 상의 객체 동기화 (직렬화 응답에 반영)

        # 대여 상태 확인: Service Layer에서 판단 ("none" | "valid" | "expired")
        # 단, 본인의 강의인 경우 항상 "valid" 처리
        rental_status = "none"
        if request.user.is_authenticated:
            if lecture.instructor.user == request.user:
                rental_status = "valid"
            else:
                from .services import get_lecture_rental_status
                rental_status = get_lecture_rental_status(request.user, lecture)

        # (1) 강의 기본 정보 직렬화
        # context에 request를 전달해야 video 등 FileField URL이 절대경로로 반환됨
        lecture_data = LectureDetailSerializer(lecture, context={"request": request}).data

        # (2) 프리뷰 강의 — 같은 강사의 is_preview=True 영상 (현재 강의 제외)
        preview = Lecture.objects.filter(
            instructor=lecture.instructor, is_preview=True
        ).exclude(pk=pk).first()
        preview_data = LecturePreviewSerializer(preview, context={"request": request}).data if preview else None

        # (3) 추천 강의 — 동일 과목을 가진 강의 중 좋아요+조회수 기준 상위 10개
        subject_ids = list(lecture.subjects.values_list("id", flat=True))
        recommended_qs = (
            Lecture.objects.filter(subjects__id__in=subject_ids)
            .exclude(pk=pk)
            .distinct()
            .annotate(like_count=Count("likes", distinct=True))
            .order_by("-like_count", "-view_count", "-created_at")[:10]
        )
        recommended_data = LectureRecommendSerializer(recommended_qs, many=True, context={"request": request}).data

        logger.info(
            "[LECTURE_DETAIL] 조회 성공. user_id=%s, lecture_id=%s, rental_status=%s",
            request.user.pk, pk, rental_status
        )
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
    URL: /lectures/<lecture_id>/comments/

    특정 강의의 '댓글(Comment)' 목록을 조회하고 새 댓글을 작성하는 API View입니다.

    목록 조회 시 부모 댓글(최상위)만 가져오며, 대댓글(replies)은 중첩되어 반환됩니다.
    
    Path Parameters:
        lecture_id (int): 댓글을 달 대상 강의 ID.

    HTTP Methods:
        GET: 강의 댓글 리스트 반환 (대댓글 포함).
        POST: 새 댓글 또는 대댓글 작성.

    Request Body (POST):
        content (str): 댓글 내용.
        parent (int, optional): 대댓글인 경우 부모 댓글 ID.
        referenced_person (int, optional): 멘션 대상의 User ID.
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CommentWriteSerializer
        return CommentSerializer

    def get_queryset(self):
        lecture_id = self.kwargs["lecture_id"]
        qs = Comment.objects.filter(lecture_id=lecture_id, parent__isnull=True).select_related("author", "referenced_person")
        
        if self.request.user.is_authenticated:
            blocked_user_ids = get_blocked_user_ids(self.request.user)
            if blocked_user_ids:
                from django.db.models import Prefetch
                qs = qs.exclude(author_id__in=blocked_user_ids).prefetch_related(
                    Prefetch(
                        "replies",
                        queryset=Comment.objects.exclude(author_id__in=blocked_user_ids)
                        .select_related("author", "referenced_person")
                        .order_by("created_at")
                    )
                )
            else:
                qs = qs.prefetch_related("replies", "replies__author", "replies__referenced_person")
        else:
            qs = qs.prefetch_related("replies", "replies__author", "replies__referenced_person")
            
        return qs.order_by("-created_at")

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
    URL: /lectures/comments/<pk>/

    본인이 작성한 '댓글(Comment)'의 내용을 수정하거나 삭제하는 API View입니다.

    자신이 작성한 댓글(`author=request.user`)만 조작 가능하도록 제한됩니다.

    Path Parameters:
        pk (int): 수정/삭제할 댓글 ID.

    HTTP Methods:
        PATCH: 댓글 내용 일부 수정.
        DELETE: 댓글 완전 삭제.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CommentWriteSerializer

    def get_queryset(self):
        return Comment.objects.filter(author=self.request.user)


# ════════════════════════════════════════════════════════════════════
# 6) Search History Views (Create / Delete)
# ════════════════════════════════════════════════════════════════════

MAX_SEARCH_HISTORY = 5  # 학생당 최대 검색 기록 수


class SearchHistoryCreateAPIView(generics.ListCreateAPIView):
    """
    URL: /lectures/search-history/

    학생 유저의 '최근 검색 기록(SearchHistory)'을 조회하고 저장하는 API View입니다.

    학생 계정(student_profile)만 이용 가능하며, 개인당 최대 5개까지만 보관됩니다.
    5개 초과 저장 시 가장 오래된 기록을 자동으로 삭제하여 FIFO를 유지합니다.

    HTTP Methods:
        GET: 본인의 검색 기록 최근순 반환.
        POST: 새로운 검색어 저장.

    Request Body (POST):
        query (str): 검색한 키워드.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SearchHistorySerializer

    def get_queryset(self):
        """
        현재 인증된 학생의 검색 기록만 반환합니다.
        강사 계정처럼 student_profile이 없는 유저의 경우 빈 쿼리셋을 반환하여
        AttributeError(500) 대신 빈 배열([])로 안전하게 응답합니다.
        """
        student = getattr(self.request.user, 'student_profile', None)
        if not student:
            return SearchHistory.objects.none()
        return SearchHistory.objects.filter(student=student).order_by("-created_at")

    def perform_create(self, serializer):
        """
        검색 기록을 저장합니다.
        - student_profile이 없는 유저는 PermissionDenied로 차단합니다.
        - 저장 후 학생당 최대 5개 초과 시 가장 오래된 기록을 자동 삭제합니다.
          (order_by("-created_at")를 명시하여 .last()가 항상 가장 오래된 것을 반환하도록 보장)
        """
        student = getattr(self.request.user, 'student_profile', None)
        if not student:
            logger.warning(
                "[SEARCH_HISTORY] 검색 기록 저장 실패 — 학생 프로필 없음. user_id=%s",
                self.request.user.pk
            )
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("학생 프로필이 필요합니다.")

        serializer.save(student=student)
        logger.debug(
            "[SEARCH_HISTORY] 검색 기록 저장. student_id=%s, query=%s",
            student.pk, serializer.instance.query if hasattr(serializer.instance, 'query') else ''
        )

        # 최대 개수 초과 시 가장 오래된 기록 삭제 (명시적 order_by로 삭제 대상 보장)
        qs = SearchHistory.objects.filter(student=student).order_by("-created_at")
        if qs.count() > MAX_SEARCH_HISTORY:
            oldest = qs.last()  # order_by("-created_at") 덕분에 .last() = 가장 오래된 레코드
            if oldest:
                oldest.delete()
                logger.debug(
                    "[SEARCH_HISTORY] 초과 기록 자동 삭제. student_id=%s, deleted_id=%s",
                    student.pk, oldest.pk
                )



class SearchHistoryDeleteAPIView(generics.DestroyAPIView):
    """
    URL: /lectures/search-history/<pk>/

    학생 유저가 자신의 '검색 기록(SearchHistory)' 중 하나를 개별 삭제하는 API View입니다.

    본인(`student=request.user.student_profile`)의 기록에만 접근할 수 있습니다.

    Path Parameters:
        pk (int): 삭제할 검색 기록 ID.
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
    URL: /lectures/<pk>/like/

    학생이 특정 VOD '강의(Lecture)'를 '찜(좋아요)' 하거나 취소(Toggle)하는 API View입니다.

    학생 계정(Student)만 접근 가능하며, 호출 시마다 상태가 토글됩니다.

    Path Parameters:
        pk (int): 대상 강의 ID.

    Returns:
        Response: {"is_liked": True/False, "like_count": 총 좋아요 수}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """
        강의 좋아요를 토글합니다.
        - 이미 좋아요를 눌렀으면 취소(remove), 안 눌렀으면 추가(add)
        - 강사 계정은 학생 프로필이 없으므로 404 반환
        """
        from config.apps.accounts.models import Student

        lecture = get_object_or_404(Lecture, pk=pk)
        student = get_object_or_404(Student, user=request.user)

        if lecture.likes.filter(pk=student.pk).exists():
            lecture.likes.remove(student)
            is_liked = False
            logger.debug(
                "[LECTURE_LIKE] 좋아요 취소. student_id=%s, lecture_id=%s",
                student.pk, pk
            )
        else:
            lecture.likes.add(student)
            is_liked = True
            logger.debug(
                "[LECTURE_LIKE] 좋아요 추가. student_id=%s, lecture_id=%s",
                student.pk, pk
            )

        return Response({
            "is_liked": is_liked,
            "like_count": lecture.likes.count()
        }, status=status.HTTP_200_OK)

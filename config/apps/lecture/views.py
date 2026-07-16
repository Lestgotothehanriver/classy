import logging
from rest_framework import generics, mixins, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from django.db import transaction
from django.db.models import Count, F, Q, Exists, OuterRef, Value, BooleanField
from django.shortcuts import get_object_or_404
from config.apps.block.utils import get_blocked_user_ids, users_have_block_relation

from config.apps.accounts.models import Instructor, Student
from config.apps.common.permissions import IsInstructorUser
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

    강사 권한을 가진 유저가 새로운 VOD 강의를 업로드하거나(POST), 기존 강의를 수정(PUT/PATCH) 및 삭제(DELETE)할 수 있습니다.
    새로운 프리뷰 강의(is_preview=True)를 업로드하면 기존 프리뷰 강의는 자동으로 삭제되어 강사당 1개의 프리뷰 영상만 유지하도록 처리하며, 해당 연산은 트랜잭션 하에서 안전하게 수행됩니다.
    또한, stop-sales 액션을 호출하여 특정 강의의 판매 상태를 중지(is_active=False)할 수 있습니다.

    Path Parameters:
        pk (int): 관리할 강의 ID.

    Request Body (POST /lectures/write/):
        title (str): 강의 제목.
        content (str): 강의 설명.
        video (File): 강의 영상 파일.
        thumbnail (File): 강의 썸네일 이미지.
        price (int): 강의 가격.
        is_preview (bool, optional): 프리뷰 영상 여부.

    Returns:
        Response (POST /lectures/write/): LectureWriteSerializer 데이터 (HTTP 201 Created)
        Response (PUT/PATCH /lectures/write/<pk>/): LectureWriteSerializer 데이터
        Response (POST /lectures/write/<pk>/stop-sales/): {
            "detail": "강의 판매가 중지되었습니다.",
            "is_active": False
        }
        Response (DELETE /lectures/write/<pk>/): HTTP 204 No Content
    """
    permission_classes = [permissions.IsAuthenticated, IsInstructorUser]
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
        판매 중지된 강의는 탐색 목록에서 노출되지 않고 신규 대여도 차단됩니다.
        전환 시점(suspended_at)을 기록하여 삭제 grace 기간 계산에 사용합니다.

        URL: POST /lectures/write/<pk>/stop-sales/
        """
        from django.utils import timezone
        lecture = self.get_object()
        lecture.is_active = False
        lecture.suspended_at = timezone.now()
        lecture.save(update_fields=['is_active', 'suspended_at'])
        logger.info(
            "[LECTURE] 강의 판매 중지. instructor_id=%s, lecture_id=%s",
            request.user.pk, pk
        )
        return Response({"detail": "강의 판매가 중지되었습니다.", "is_active": False}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='resume-sales')
    def resume_sales(self, request, pk=None):
        """
        판매 중지된 강의의 판매를 재개합니다. (is_active=True로 변경, suspended_at 초기화)
        영상 파일을 다시 올리는 것이 아니라, 동일 강의를 판매대에 다시 올리는 동작입니다.

        URL: POST /lectures/write/<pk>/resume-sales/
        """
        lecture = self.get_object()
        lecture.is_active = True
        lecture.suspended_at = None
        lecture.save(update_fields=['is_active', 'suspended_at'])
        logger.info(
            "[LECTURE] 강의 판매 재개. instructor_id=%s, lecture_id=%s",
            request.user.pk, pk
        )
        return Response({"detail": "강의 판매가 재개되었습니다.", "is_active": True}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        강의를 소프트 삭제합니다. (하드 삭제 대신 is_delete=True/deleted_at 세팅)

        삭제 자격은 services.get_lecture_delete_eligibility로 판정하며, 아직 삭제할 수 없는
        경우 409로 사유(code)를 반환한다.
          - grace_period: 판매 중지 후 30일 미경과 → {"code","deletable_in_days"}
          - active_renter: 현재 대여중 학생 존재 → {"code"}
        소프트 삭제 시 대여/정산 이력(LectureRentalHistory)은 CASCADE로 삭제되지 않고 보존된다.
        """
        from django.utils import timezone
        from .services import get_lecture_delete_eligibility

        lecture = self.get_object()
        eligibility, days_remaining = get_lecture_delete_eligibility(lecture)

        if eligibility == "grace_period":
            return Response(
                {"code": "grace_period", "deletable_in_days": days_remaining},
                status=status.HTTP_409_CONFLICT,
            )
        if eligibility == "active_renter":
            return Response(
                {"code": "active_renter"},
                status=status.HTTP_409_CONFLICT,
            )

        lecture.is_delete = True
        lecture.is_active = False
        lecture.deleted_at = timezone.now()
        lecture.save(update_fields=['is_delete', 'is_active', 'deleted_at'])
        logger.info(
            "[LECTURE] 강의 소프트 삭제. instructor_id=%s, lecture_id=%s",
            request.user.pk, lecture.pk
        )
        return Response({"code": "deleted"}, status=status.HTTP_200_OK)


# ════════════════════════════════════════════════════════════════════
# 2) Lecture Filtering & List
# ════════════════════════════════════════════════════════════════════

class LectureListAPIView(generics.ListAPIView):
    """
    URL: /lectures/

    판매 중(is_active=True)인 전체 '강의 목록'을 조회하고 필터링하는 API View입니다.

    학생들이 강의를 검색할 수 있도록 다중 키워드(q), 과목 번호 리스트(subject), 최대 가격(max_price), 영상 길이 범위(video_length), 강사의 지역 및 소속(region, university, department, student_number) 등 복합 필터링을 제공합니다.
    인증된 학생 유저가 요청하는 경우 차단된 강사의 강의는 목록에서 제외되며, 서브쿼리를 이용하여 로그인한 학생의 각 강의 찜(좋아요) 여부를 동적으로 계산하여 응답에 포함합니다.

    Query Parameters:
        q (str, optional): 제목/과목/강사명/대학/학과 등 통합 검색어.
        subject (str, optional): 과목 ID 목록 (콤마 구분).
        max_price (int, optional): 최대 가격 제한.
        video_length (str, optional): 영상 길이 범위 ('under_5' | '10_30' | '30_60' | '60_90' | 'over_90').
        region (str, optional): 강사 활동 지역 목록 (콤마 구분).
        university (str, optional): 강사 소속 대학교명.
        department (str, optional): 강사 소속 학과명.
        student_number (str, optional): 강사 학번 목록 (콤마 구분).
        liked (bool, optional): 본인이 찜한 강의만 필터링할지 여부.
        is_tutoring (bool, optional): 과외 가능 여부 필터.
        instructor (str, optional): 'me' 입력 시 본인의 강의만 필터링하거나 강사 ID로 필터링.

    Returns:
        Response: List[LectureListSerializer] 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LectureListSerializer

    def get_queryset(self):
        # 강사가 본인 강의를 조회(instructor=me)하는 경우에만 판매 중지(is_active=False) 강의를 포함한다.
        # 그 외(학생 브라우즈, 타 강사 프로필)는 판매중(is_active=True)만 노출. 소프트삭제는 항상 숨김.
        instructor_param = self.request.query_params.get("instructor")
        is_own = instructor_param == "me" and self.request.user.is_authenticated

        qs = Lecture.objects.filter(is_delete=False)
        if not is_own:
            qs = qs.filter(is_active=True)
        qs = qs.select_related(
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

    요청받은 강의가 무료(price=0), 프리뷰용 강의(is_preview=True), 강사 본인의 강의인 경우 권한을 패스합니다.
    그 외의 유료 강의는 로그인한 사용자의 LectureRentalHistory 대여 이력을 조회하여 현재 시점 기준 유효한 대여 상태("valid")인지 검증합니다.
    대여 내역이 없거나 만료된 경우에는 403 에러를 반환합니다.

    Path Parameters:
        pk (int): 재생하려는 강의 ID.

    Returns:
        Response: LectureStreamSerializer 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LectureStreamSerializer
    queryset = Lecture.objects.filter(is_delete=False)

    def get_queryset(self):
        qs = super().get_queryset()
        blocked_user_ids = get_blocked_user_ids(self.request.user)
        if blocked_user_ids:
            qs = qs.exclude(instructor__user_id__in=blocked_user_ids)
        return qs

    def retrieve(self, request, *args, **kwargs):
        """
        강의 영상 스트리밍 URL을 반환합니다.
        - price=0 또는 is_preview=True인 경우: 누구나 무료로 시청 가능합니다.
        - price>0 이고 is_preview=False인 경우: 유효한 대여 이력이 없으면 403 반환합니다.
          (대여 만료 여부는 Service Layer의 has_valid_rental에서 처리)
        """
        lecture = self.get_object()
        logger.debug(
            "[STREAM] 스트리밍 요청. user_id=%s, lecture_id=%s, price=%s, is_preview=%s",
            request.user.pk, lecture.pk, lecture.price, lecture.is_preview
        )

        # 무료 강의, 프리뷰 강의, 강사 본인 강의는 대여 없이 스트리밍을 허용한다.
        if lecture.price > 0 and not lecture.is_preview and lecture.instructor.user != request.user:
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
        from .utils import normalize_field_file_for_mobile_playback
        if normalize_field_file_for_mobile_playback(lecture.video):
            lecture.save(update_fields=["video"])
            logger.info(
                "[STREAM] 모바일 재생 호환 포맷으로 영상 변환 완료. lecture_id=%s",
                lecture.pk
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
        blocked_user_ids = get_blocked_user_ids(request.user)
        if blocked_user_ids:
            qs = qs.exclude(instructor__user_id__in=blocked_user_ids)

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

        # (2) 프리뷰 강의 — 같은 강사의 is_preview=True 영상 (현재 강의 제외, 판매중지/삭제 제외)
        preview = Lecture.objects.filter(
            instructor=lecture.instructor, is_preview=True, is_active=True, is_delete=False
        ).exclude(pk=pk).first()
        preview_data = LecturePreviewSerializer(preview).data if preview else None

        # (3) 추천 강의 — 동일 과목을 가진 강의 중 좋아요+조회수 기준 상위 10개 (판매중지/삭제 제외)
        subject_ids = list(lecture.subjects.values_list("id", flat=True))
        recommended_qs = (
            Lecture.objects.filter(subjects__id__in=subject_ids, is_active=True, is_delete=False)
            .exclude(pk=pk)
            .exclude(instructor__user_id__in=blocked_user_ids)
            .distinct()
            .annotate(like_count=Count("likes", distinct=True))
            .order_by("-like_count", "-view_count", "-created_at")[:10]
        )
        recommended_data = LectureRecommendSerializer(recommended_qs, many=True).data

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

    GET 요청 시, 특정 강의에 작성된 최상위 부모 댓글 목록만 정렬하여 가져오며, 각 부모 댓글 객체 안에 대댓글(replies) 리스트가 중첩되어 반환됩니다. 차단한 유저의 댓글 및 대댓글은 목록에서 제외됩니다.
    POST 요청 시, 로그인한 사용자의 새 댓글 또는 대댓글 작성을 처리하며, 대댓글의 경우 부모 댓글(parent) ID 및 언급 대상 유저(referenced_person) ID를 추가로 전달받아 연결합니다.

    Path Parameters:
        lecture_id (int): 댓글을 작성하거나 조회할 강의 ID.

    Request Body (POST):
        content (str): 댓글 내용.
        parent (int, optional): 대댓글인 경우 부모 댓글 ID.
        referenced_person (int, optional): 멘션 대상의 User ID.

    Returns:
        Response (GET): List[CommentSerializer] 데이터
        Response (POST): CommentSerializer 데이터 (HTTP 201 Created)
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
        # 소프트 삭제된 강의에는 댓글 작성 불가 (is_delete=False).
        lecture = get_object_or_404(Lecture, pk=self.kwargs["lecture_id"], is_delete=False)
        if users_have_block_relation(self.request.user, lecture.instructor.user):
            raise PermissionDenied("차단 관계인 사용자의 강의에는 댓글을 작성할 수 없습니다.")
        serializer.save(author=self.request.user, lecture=lecture)

    def create(self, request, *args, **kwargs):
        # lecture 필드를 URL에서 자동 할당하므로, request.data에 lecture가 없어도 처리
        data = request.data.copy()
        data["lecture"] = self.kwargs["lecture_id"]
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # 저장된 객체를 읽기 Serializer로 반환
        # context(request)를 전달해야 is_mine 판별과 프로필 이미지 절대경로가 정상 동작함
        output = CommentSerializer(
            serializer.instance, context=self.get_serializer_context()
        ).data
        return Response(output, status=status.HTTP_201_CREATED)


class CommentUpdateDeleteAPIView(generics.UpdateAPIView, generics.DestroyAPIView):
    """
    URL: /lectures/comments/<pk>/

    본인이 작성한 '댓글(Comment)'의 내용을 수정하거나 삭제하는 API View입니다.

    자신이 작성한 댓글(author=request.user)만 수정(PATCH) 또는 삭제(DELETE)가 가능합니다.
    PATCH 요청 시 전달받은 내용으로 댓글의 본문(content)을 변경하고, DELETE 요청 시 데이터베이스에서 완전히 삭제합니다.

    Path Parameters:
        pk (int): 수정/삭제할 댓글 ID.

    Request Body (PATCH):
        content (str): 수정할 댓글 내용.

    Returns:
        Response (PATCH): CommentWriteSerializer 데이터
        Response (DELETE): HTTP 204 No Content
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

    GET 요청 시, 로그인한 학생의 최근 검색 기록을 최대 5개까지 최신순으로 조회하여 반환합니다. 학생 프로필이 없는 경우 빈 목록이 반환됩니다.
    POST 요청 시, 새로운 검색 키워드를 생성하여 저장하며, 해당 학생의 저장된 검색 기록이 5개를 초과하게 될 경우, 가장 오래된 검색 기록을 데이터베이스에서 자동으로 조회하여 삭제하는 FIFO 정책을 원자적으로 수행합니다.

    Request Body (POST):
        query (str): 검색한 키워드.

    Returns:
        Response (GET): List[SearchHistorySerializer] 데이터
        Response (POST): SearchHistorySerializer 데이터 (HTTP 201 Created)
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

    로그인한 학생 유저 본인의 검색 기록(student=request.user.student_profile)에만 한정하여 조회가 가능하며, DELETE 호출 시 해당 기록을 데이터베이스에서 즉시 삭제합니다.

    Path Parameters:
        pk (int): 삭제할 검색 기록 ID.

    Returns:
        Response: HTTP 204 No Content
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

    학생 계정(Student)을 가진 유저만 강의 찜하기(좋아요) 토글이 가능합니다.
    POST 호출 시, 이미 해당 강의를 찜한 학생의 경우 찜 관계를 제거하고, 그렇지 않은 경우 찜 관계를 추가한 후 최종 찜 여부와 찜의 누적 총 개수를 계산하여 반환합니다. 강사 등 학생 프로필이 없는 계정은 404를 반환합니다.

    Path Parameters:
        pk (int): 대상 강의 ID.

    Returns:
        Response: {
            "is_liked": bool,
            "like_count": int
        }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """
        강의 좋아요를 토글합니다.
        - 이미 좋아요를 눌렀으면 취소(remove), 안 눌렀으면 추가(add)
        - 강사 계정은 학생 프로필이 없으므로 404 반환
        """
        from config.apps.accounts.models import Student

        # 소프트 삭제된 강의는 찜(좋아요) 토글 불가 (is_delete=False).
        lecture = get_object_or_404(Lecture, pk=pk, is_delete=False)
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

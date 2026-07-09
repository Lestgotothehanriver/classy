from rest_framework import generics, permissions
from django.db.models import Avg, Count, F, ExpressionWrapper, FloatField, OuterRef, Subquery, Value, BooleanField
from django.db.models import IntegerField as DjangoIntField
from django.shortcuts import get_object_or_404
import logging
from rest_framework.response import Response
from config.apps.block.utils import get_blocked_user_ids

from config.apps.accounts.models import Instructor, Student, InstructorLike
from config.apps.cash.models import InstructorMonthlyRank
from config.apps.common.utils import parse_int_list, apply_subject_filter
from ..models import InstructorInfo, InstructorReview
from ..serializers import InstructorListSerializer, InstructorInfoSerializer, InstructorReviewSerializer
from config.apps.common.mixins import InstructorAnnotateMixin

logger = logging.getLogger(__name__)

class InstructorListAPIView(generics.ListAPIView, InstructorAnnotateMixin):
    """
    URL: /tutoring/instructors/

    과외 강사 목록을 조회하고 필터링하는 API View입니다.

    GET 요청 시, 검색 키워드(search), 정렬 기준(ordering), 찜 여부(liked), 과목 필터(subject), 지역 필터(region), 성별(sex), 나이대(age), 출신 학교명(university), 학과명(department) 등의 쿼리 스트링 조건에 기반하여 가입된 강사 중 차단한 강사를 제외한 목록을 최신순 혹은 인기순으로 반환합니다.

    Query Parameters:
        ordering (str, optional): 정렬 기준 ('latest' | 'likes', 기본값 'latest').
        liked (bool, optional): 본인이 찜한 강사만 볼지 여부.
        subject (str, optional): 과목 ID 목록 (콤마 구분, 예: '1,2').
        region (str, optional): 지역 ID 목록 (콤마 구분, 예: '11110,11120').
        cost (int, optional): 최대 수업료 상한액 필터.
        method (str, optional): 수업 방식 ('ONLINE' | 'OFFLINE', 콤마 구분 가능).
        sex (str, optional): 강사 성별 ('M' | 'F').
        age (str, optional): 강사 나이 또는 나이 범위 (콤마 구분, 예: '25-30,35').
        university (str, optional): 대학교명 키워드 검색.
        department (str, optional): 학과명 키워드 검색.
        search (str, optional): 이름/학교/학과/지역/소개글 통합 검색어.
        student_id (str, optional): 학번/사번 필터링용 접두사 목록 (콤마 구분).

    Returns:
        Response: List[InstructorListSerializer] 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorListSerializer

    def get_queryset(self):
        qs = Instructor.objects.all().select_related("tutoring_profile")

        if self.request.user.is_authenticated:
            blocked_user_ids = get_blocked_user_ids(self.request.user)
            if blocked_user_ids:
                qs = qs.exclude(user_id__in=blocked_user_ids)

        qs = self.annotate_instructor_stats(qs, self.request.user)

        ordering = self.request.query_params.get("ordering", "latest")
        if ordering == "likes":
            qs = qs.order_by("-like_count", "-id")
        else:
            qs = qs.order_by("-id")

        liked = self.request.query_params.get("liked")
        if liked is not None:
            qs = qs.filter(is_liked=(liked.lower() in ("true", "1")))

        subject_ids = parse_int_list(self.request.query_params.get("subject"))
        qs = apply_subject_filter(qs, Instructor, subject_ids, prefix="tutoring_profile__")

        region_ids = parse_int_list(self.request.query_params.get("region"))
        if region_ids:
            qs = qs.filter(tutoring_profile__regions__number__in=region_ids).distinct()

        cost = self.request.query_params.get("cost")
        if cost and cost.isdigit():
            qs = qs.filter(tutoring_profile__cost__lte=int(cost))

        method = self.request.query_params.get("method")
        if method:
            from django.db.models import Q
            method_list = [m.strip() for m in method.split(',') if m.strip()]
            q = Q()
            for m in method_list:
                q |= Q(tutoring_profile__method__icontains=m)
            qs = qs.filter(q).distinct()

        sex = self.request.query_params.get("sex")
        if sex:
            qs = qs.filter(user__sex=sex)

        age_param = self.request.query_params.get("age")
        if age_param:
            from django.utils import timezone
            current_year = timezone.now().year
            from django.db.models import Q
            age_parts = age_param.split(",")
            q = Q()
            for part in age_parts:
                part = part.strip()
                if "-" in part:
                    bounds = part.split("-", 1)
                    if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                        min_age, max_age = int(bounds[0]), int(bounds[1])
                        min_year = current_year - max_age
                        max_year = current_year - min_age
                        q |= Q(user__birth_date__year__gte=min_year, user__birth_date__year__lte=max_year)
                elif part.isdigit():
                    age = int(part)
                    target_year = current_year - age
                    q |= Q(user__birth_date__year=target_year)
            if q:
                qs = qs.filter(q)

        university = self.request.query_params.get("university")
        if university:
            qs = qs.filter(university__icontains=university)

        department = self.request.query_params.get("department")
        if department:
            qs = qs.filter(department__icontains=department)

        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q
            q = Q(user__user_name__icontains=search) | \
                Q(university__icontains=search) | \
                Q(department__icontains=search) | \
                Q(user__region__icontains=search) | \
                Q(student_number__icontains=search) | \
                Q(tutoring_profile__subjects__name__icontains=search)
            qs = qs.filter(q).distinct()

        student_no = self.request.query_params.get("student_id")
        if student_no:
            from django.db.models import Q
            no_list = [n.strip() for n in student_no.split(",") if n.strip().isdigit()]
            if no_list:  # 유효한 숫자 값이 있을 때만 필터 적용
                q = Q()
                for n in no_list:
                    q |= Q(student_number__startswith=n)
                qs = qs.filter(q)

        return qs

class InstructorDetailAPIView(generics.RetrieveAPIView, InstructorAnnotateMixin):
    """
    URL: /tutoring/instructors/<pk>/

    특정 강사의 상세 프로필 정보를 조회하는 API View입니다.

    GET 요청 시, 강사 식별자(pk)를 활용하여 해당 강사의 기본 인적 사항, 출신 대학교/학과, 찜 수(like_count), 평균 별점(avg_rating) 및 로그인한 유저의 찜 여부(is_liked) 데이터를 포함한 프로필 상세를 조회하여 반환합니다.

    Path Parameters:
        pk (int): 대상 강사의 ID.

    Returns:
        Response: InstructorListSerializer 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorListSerializer

    def get_queryset(self):
        qs = Instructor.objects.all().select_related("tutoring_profile")
        return self.annotate_instructor_stats(qs, self.request.user)

class InstructorInfoAPIView(generics.RetrieveAPIView):
    """
    URL: /tutoring/instructors/<instructor_id>/info/

    특정 강사의 과외 소개 및 상세 통계 탭 정보를 조회하는 API View입니다.

    GET 요청 시, 강사가 작성한 자기소개 본문(description), 수업 방식(method), 소속 및 전문 분야를 비롯하여 강사의 평점 내역 평균치(avg_rating), 총 리뷰 개수(review_count), 최신 월간 순위(current_rank)를 종합 집계하여 제공합니다.

    Path Parameters:
        instructor_id (int): 대상 강사의 Instructor ID.

    Returns:
        Response: InstructorInfoSerializer 데이터 + 추가 집계 통계 객체 (avg_rating, review_count, current_rank, is_tutoring 포함)
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorInfoSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = get_object_or_404(InstructorInfo, instructor_id=kwargs["instructor_id"])
        serializer = self.get_serializer(instance)
        data = serializer.data

        instructor = instance.instructor

        stats = InstructorReview.objects.filter(instructor=instructor).aggregate(
            avg_rating=Avg(
                ExpressionWrapper(
                    (F("professionalism") + F("teaching_skill") + F("punctuality")) / 3.0,
                    output_field=FloatField()
                )
            ),
            review_count=Count("id")
        )
        data["avg_rating"] = stats["avg_rating"]
        data["review_count"] = stats["review_count"] or 0

        latest_rank = (
            InstructorMonthlyRank.objects.filter(instructor=instructor)
            .order_by("-year", "-month")
            .values("rank")
            .first()
        )
        data["current_rank"] = latest_rank["rank"] if latest_rank else None
        data["is_tutoring"] = instructor.is_tutoring

        return Response(data)

class InstructorReviewListAPIView(generics.ListAPIView):
    """
    URL: /tutoring/instructors/<instructor_id>/reviews/

    특정 강사에게 등록된 모든 리뷰 목록을 조회하는 API View입니다.

    GET 요청 시, 해당 강사가 과거 과외 학생들로부터 받은 모든 평가 항목(전문성, 교수법, 시간 준수 등)과 리뷰 글 및 평가 과목 목록을 최신순으로 정렬하여 반환하며 차단된 학생 유저가 남긴 리뷰는 제외합니다.

    Path Parameters:
        instructor_id (int): 리뷰 대상 강사의 ID.

    Returns:
        Response: List[InstructorReviewSerializer] 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorReviewSerializer

    def get_queryset(self):
        instructor_id = self.kwargs["instructor_id"]
        qs = InstructorReview.objects.filter(instructor_id=instructor_id)
        
        if self.request.user.is_authenticated:
            blocked_user_ids = get_blocked_user_ids(self.request.user)
            if blocked_user_ids:
                qs = qs.exclude(student__user_id__in=blocked_user_ids)
                
        return qs.prefetch_related("subjects").order_by("-id")

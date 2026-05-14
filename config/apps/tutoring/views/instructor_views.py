from rest_framework import generics, permissions
from django.db.models import Avg, Count, F, ExpressionWrapper, FloatField, OuterRef, Subquery, Value, BooleanField
from django.db.models import IntegerField as DjangoIntField
from django.shortcuts import get_object_or_404
import logging

from config.apps.accounts.models import Instructor, Student, InstructorLike
from config.apps.cash.models import InstructorMonthlyRank
from config.apps.common.utils import parse_int_list, apply_subject_filter
from ..models import InstructorInfo, InstructorReview
from ..serializers import InstructorListSerializer, InstructorInfoSerializer, InstructorReviewSerializer
from config.apps.common.mixins import InstructorAnnotateMixin

logger = logging.getLogger(__name__)

class InstructorListAPIView(generics.ListAPIView, InstructorAnnotateMixin):
    """
    승인 완료된 '강사 목록'을 조회하고 필터링하는 API View입니다.

    Query Parameters:
        ordering (str): 정렬 기준 ('latest' | 'likes').
        liked (bool): 본인이 찜한 강사만 볼지 여부.
        subject (str): 과목 ID 목록 (콤마 구분, 예: '1,2').
        region (str): 지역 키워드 (파이프 구분, 예: '서울|강남').
        cost (int): 최대 과외비 상한.
        method (str): 수업 방식 ('ONLINE' | 'OFFLINE').
        search (str): 통합 검색어 (닉네임, 지역, 대학 등).

    Response (JSON):
        HTTP 200 OK:
        [
            {
                "id": 5,
                "user_name": "강사님",
                "university": "서울대학교",
                "department": "컴퓨터공학",
                "like_count": 25,
                "is_liked": true,
                "avg_rating": 4.8
            }
        ]
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorListSerializer

    def get_queryset(self):
        qs = Instructor.objects.filter(pending_info__status='VERIFIED')
        qs = qs.select_related("tutoring_profile")

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
        qs = apply_subject_filter(qs, Instructor, subject_ids)

        region = self.request.query_params.get("region")
        if region:
            from django.db.models import Q
            region_list = [r.strip() for r in region.split('|') if r.strip()]
            q = Q()
            for r in region_list:
                q |= Q(user__region__icontains=r)
            qs = qs.filter(q).distinct()

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
    특정 강사의 상세 프로필 정보를 조회하는 API View입니다.

    Path Parameters:
        pk (int): 강사의 ID.

    Response (JSON):
        HTTP 200 OK:
        {
            "id": 5,
            "user_name": "강사님",
            "instruction": "꼼꼼하게 가르칩니다.",
            "university": "서울대학교",
            "subjects": ["수학", "영어"],
            "like_count": 25,
            "avg_rating": 4.8,
            "reviews": [...]
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorListSerializer

    def get_queryset(self):
        qs = Instructor.objects.filter(pending_info__status='VERIFIED')
        qs = qs.select_related("tutoring_profile")
        return self.annotate_instructor_stats(qs, self.request.user)

class InstructorInfoAPIView(generics.RetrieveAPIView):
    """
    특정 강사가 직접 작성한 '과외 소개(InstructorInfo)' 상세 탭 데이터를 조회하는 API View입니다.

    기본 프로필 외에, 강사의 자기소개(description), 수업 방식(method), 
    진행 중인 과외 횟수, 월간 랭킹 정보(InstructorMonthlyRank), 그리고 리뷰 요약(평균)을 반환합니다.

    Path Parameters:
        pk (int): 강사의 Instructor ID.

    Returns:
        InstructorInfoSerializer: 강사 과외 상세 소개 정보.
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
    특정 강사가 학생들로부터 받은 '강사 리뷰(InstructorReview)' 목록을 조회하는 API View입니다.

    Path Parameters:
        instructor_id (int): 리뷰 대상 강사의 ID.

    Returns:
        List[InstructorReviewSerializer]: 해당 강사가 받은 리뷰 리스트.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorReviewSerializer

    def get_queryset(self):
        instructor_id = self.kwargs["instructor_id"]
        return InstructorReview.objects.filter(
            instructor_id=instructor_id
        ).prefetch_related("subjects").order_by("-id")

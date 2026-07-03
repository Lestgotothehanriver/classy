from rest_framework import generics, permissions, viewsets, mixins
from django.db.models import Avg, Count, F
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
import logging
from config.apps.block.utils import get_blocked_user_ids

from config.apps.accounts.models import Student, Instructor
from config.apps.common.utils import parse_int_list, apply_subject_filter
from ..models import TutoringPost
from ..serializers import TutoringPostListSerializer, TutoringPostDetailSerializer, TutoringPostWriteSerializer, StudentMyPostSerializer

logger = logging.getLogger(__name__)

class TutoringPostListAPIView(generics.ListAPIView):
    """
    URL: /tutoring/posts/

    학생들이 올린 활성화된 '과외 구인 공고(TutoringPost)' 목록을 조회하고 필터링하는 API View입니다.

    Query Parameters:
        ordering (str): 정렬 기준 ('latest' | 'likes').
        subject (str): 과목 ID 목록 (콤마 구분, 예: '1,2,3').
        region (str): 지역 필터 (예: '서울').
        cost (int): 최대 희망 과외비 상한선.
        method (str): 수업 방식 ('ONLINE' | 'OFFLINE' | 'BOTH').
        sex (str): 희망 학생 성별 ('M' | 'F' | 'ANY').

    Response (JSON):
        HTTP 200 OK:
        [
            {
                "id": 1,
                "title": "수학 과외 구합니다",
                "student_name": "홍길동",
                "subjects": ["수학", "미적분"],
                "cost": 300000,
                "student_avg_rating": 4.5,
                "like_count": 10,
                "created_at": "2026-04-26T06:51:26Z"
            }
        ]
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringPostListSerializer

    def get_queryset(self):
        qs = TutoringPost.objects.filter(is_active=True).select_related("student").prefetch_related("subjects")

        if self.request.user.is_authenticated:
            blocked_user_ids = get_blocked_user_ids(self.request.user)
            if blocked_user_ids:
                qs = qs.exclude(student__user_id__in=blocked_user_ids)

        qs = qs.annotate(
            student_avg_rating=Avg("student__student_reviews__rating"),
            student_review_count=Count("student__student_reviews", distinct=True),
            like_count=Count("liked_by", distinct=True),
        )

        ordering = self.request.query_params.get("ordering", "latest")
        if ordering == "likes":
            qs = qs.order_by("-like_count", "-id")
        else:
            qs = qs.order_by("-id")

        subject_ids = parse_int_list(self.request.query_params.get("subject"))
        qs = apply_subject_filter(qs, Student, subject_ids, prefix="student__")

        region = self.request.query_params.get("region")
        if region:
            qs = qs.filter(region__icontains=region)

        cost = self.request.query_params.get("cost")
        if cost and cost.isdigit():
            qs = qs.filter(cost__lte=int(cost))

        method = self.request.query_params.get("method")
        if method:
            from django.db.models import Q
            method_list = [m.strip() for m in method.split(',') if m.strip()]
            q = Q()
            for m in method_list:
                q |= Q(method__icontains=m)
            qs = qs.filter(q)

        sex = self.request.query_params.get("sex")
        if sex:
            qs = qs.filter(sex=sex)

        grade = self.request.query_params.get("grade")
        if grade:
            qs = qs.filter(grade=grade)

        min_rating = self.request.query_params.get("min_rating")
        if min_rating and min_rating.isdigit():
            qs = qs.filter(student_avg_rating__gte=float(min_rating))

        return qs

class TutoringPostDetailAPIView(generics.RetrieveAPIView):
    """
    URL: /tutoring/posts/<pk>/

    특정 '과외 구인 공고'의 상세 정보를 조회하는 API View입니다.

    조회 시 자동으로 해당 공고의 조회수(view_count)가 1 증가합니다.

    Path Parameters:
        pk (int): 조회할 공고(TutoringPost)의 Primary Key.

    Returns:
        TutoringPostDetailSerializer: 공고 상세 데이터(작성 학생 정보 및 찜 상태 등 포함).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringPostDetailSerializer
    queryset = TutoringPost.objects.select_related("student")

    def retrieve(self, request, *args, **kwargs):
        TutoringPost.objects.filter(pk=kwargs["pk"]).update(view_count=F("view_count") + 1)
        return super().retrieve(request, *args, **kwargs)

class TutoringPostViewSet(mixins.CreateModelMixin,
                          mixins.UpdateModelMixin,
                          mixins.DestroyModelMixin,
                          viewsets.GenericViewSet):
    """
    URL: /tutoring/posts/write/
    URL: /tutoring/posts/write/<pk>/

    학생이 자신의 '과외 구인 공고'를 관리(작성/수정/삭제)하는 API ViewSet입니다.

    Request (POST /):
        title (str): 공고 제목.
        content (str): 상세 요청 사항.
        cost (int): 희망 수업료.
        method (str): 수업 방식 ('ONLINE' | 'OFFLINE').
        subject_names (list): 과목명 리스트 (예: ["수학", "과학"]).

    Response (POST /):
        HTTP 201 Created:
        {
            "id": 5,
            "title": "과외 공고",
            "content": "상세 내용...",
            "cost": 250000,
            "created_at": "2026-04-26T06:51:26Z"
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringPostWriteSerializer

    def get_queryset(self):
        return TutoringPost.objects.filter(student__user=self.request.user)

    def perform_create(self, serializer):
        try:
            student = Student.objects.get(user=self.request.user)
        except Student.DoesNotExist:
            raise PermissionDenied("학생 계정만 공고를 올릴 수 있습니다.")
        serializer.save(student=student)

class StudentMyPostAPIView(generics.ListAPIView):
    """
    URL: /tutoring/my-posts/

    학생 본인이 작성했던 모든 '과외 구인 공고' 목록을 조회하는 API View입니다.

    활성화(is_active) 여부와 상관없이 본인의 작성 이력을 최신순으로 제공합니다.

    Returns:
        List[StudentMyPostSerializer]: 본인이 작성한 공고들의 리스트.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentMyPostSerializer

    def get_queryset(self):
        try:
            student = Student.objects.get(user=self.request.user)
        except Student.DoesNotExist:
            raise PermissionDenied("학생 계정만 사용할 수 있습니다.")
        return TutoringPost.objects.filter(student=student).prefetch_related("subjects").order_by("-id")

from rest_framework import generics, permissions, viewsets, mixins
from rest_framework.response import Response
from django.db.models import Avg, Count, F
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
import logging
from config.apps.block.utils import get_blocked_user_ids

from config.apps.accounts.models import Student, Instructor
from config.apps.chat_app.models import ChatRoom
from config.apps.common.utils import parse_int_list, apply_subject_filter
from ..models import TutoringPost
from ..serializers import TutoringPostListSerializer, TutoringPostDetailSerializer, TutoringPostWriteSerializer, StudentMyPostSerializer

logger = logging.getLogger(__name__)

class TutoringPostListAPIView(generics.ListAPIView):
    """
    URL: /tutoring/posts/

    학생들이 등록한 활성화 상태의 '과외 구인 공고(TutoringPost)' 목록을 조회하고 필터링하는 API View입니다.

    GET 요청 시, 검색 키워드(search), 정렬 기준(ordering), 과목 필터(subject), 희망 지역 필터(region), 희망 과외비 상한선(cost), 수업 방식(method), 학생 성별(sex), 학년(grade) 및 학생 최소 평점(min_rating) 등 입력받은 검색 필터 조건에 부합하고 차단한 학생이 작성하지 않은 활성 구인 공고 목록을 반환합니다.

    Query Parameters:
        ordering (str, optional): 정렬 기준 ('latest' | 'likes', 기본값 'latest').
        subject (str, optional): 과목 ID 목록 (콤마 구분, 예: '1,2').
        region (str, optional): 지역 ID 목록 (콤마 구분, 예: '11110,11120').
        cost (int, optional): 희망 수업료 상한선 필터.
        method (str, optional): 수업 방식 ('ONLINE' | 'OFFLINE', 콤마 구분 가능).
        sex (str, optional): 희망 학생 성별 ('M' | 'F').
        grade (str, optional): 학생 학년 코드 필터.
        min_rating (float, optional): 작성 학생의 최소 평균 평점 필터.
        search (str, optional): 제목/상황/비고/이름/과목명 통합 검색어.

    Returns:
        Response: List[TutoringPostListSerializer] 데이터
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
        qs = apply_subject_filter(qs, TutoringPost, subject_ids)

        region_ids = parse_int_list(self.request.query_params.get("region"))
        if region_ids:
            qs = qs.filter(region__number__in=region_ids).distinct()

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

        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q
            q = Q()
            q |= Q(title__icontains=search)
            q |= Q(situation__icontains=search)
            q |= Q(etc__icontains=search)
            q |= Q(student__user__user_name__icontains=search)
            q |= Q(subjects__name__icontains=search)
            qs = qs.filter(q).distinct()

        return qs

class TutoringPostDetailAPIView(generics.RetrieveAPIView):
    """
    URL: /tutoring/posts/<pk>/

    특정 '과외 구인 공고'의 상세 정보를 조회하는 API View입니다.

    GET 요청 시, 공고 ID(pk)에 해당하는 구인 공고 글 상세 항목을 조회하여 반환하며 호출 시 자동으로 공고의 조회수(view_count)를 1 증가시킵니다.

    Path Parameters:
        pk (int): 조회할 공고(TutoringPost) ID.

    Returns:
        Response: TutoringPostDetailSerializer 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringPostDetailSerializer
    queryset = TutoringPost.objects.select_related("student")

    def retrieve(self, request, *args, **kwargs):
        TutoringPost.objects.filter(pk=kwargs["pk"]).update(view_count=F("view_count") + 1)
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        has_chat_room = False
        if request.user.is_authenticated and hasattr(request.user, "instructor_profile"):
            has_chat_room = ChatRoom.objects.filter(
                student=instance.student,
                instructor=request.user.instructor_profile
            ).exists()
        data["has_chat_room"] = has_chat_room

        return Response(data)

class TutoringPostViewSet(mixins.CreateModelMixin,
                          mixins.UpdateModelMixin,
                          mixins.DestroyModelMixin,
                          viewsets.GenericViewSet):
    """
    URL: /tutoring/posts/write/
    URL: /tutoring/posts/write/<pk>/

    학생이 본인의 '과외 구인 공고'를 생성, 수정, 삭제하는 API ViewSet입니다.

    POST /tutoring/posts/write/ 요청 시, 학생 계정으로 로그인한 유저의 신규 과외 구인 공고를 등록합니다.
    PUT/PATCH /tutoring/posts/write/<pk>/ 요청 시, 본인이 작성한 특정 구인 공고 정보를 수정합니다.
    DELETE /tutoring/posts/write/<pk>/ 요청 시, 작성했던 구인 공고를 삭제합니다.

    Path Parameters:
        pk (int): 수정 또는 삭제할 공고 ID.

    Request Body (POST):
        title (str): 공고 제목 (필수).
        cost (int): 희망 수업료 (필수).
        method (str): 희망 수업 방식 ('ONLINE' | 'OFFLINE' 등, 필수).
        subject_ids (list[int]): 연관 과목 ID 목록.
        region_id (int): 희망 지역 ID.
        grade (str): 학년.
        sex (str): 성별 선호도.
        situation (str): 학생 학습 상황 설명.
        etc (str): 기타 요구 사항.

    Returns:
        Response (POST): TutoringPostWriteSerializer 데이터 (HTTP 201 Created)
        Response (PUT/PATCH): TutoringPostWriteSerializer 데이터 (HTTP 200 OK)
        Response (DELETE): HTTP 204 No Content
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

    GET 요청 시, 로그인한 학생 사용자가 이전에 올렸던 전체 공고 목록을 활성화 여부(is_active)와 상관없이 최신순으로 정렬하여 반환합니다. 학생 계정이 아닐 시 403 예외가 발생합니다.

    Returns:
        Response: List[StudentMyPostSerializer] 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentMyPostSerializer

    def get_queryset(self):
        try:
            student = Student.objects.get(user=self.request.user)
        except Student.DoesNotExist:
            raise PermissionDenied("학생 계정만 사용할 수 있습니다.")
        return TutoringPost.objects.filter(student=student).prefetch_related("subjects").order_by("-id")

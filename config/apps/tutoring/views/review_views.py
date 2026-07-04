from rest_framework import generics, permissions, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
import logging
from config.apps.block.utils import get_blocked_user_ids

from config.apps.accounts.models import Student, Instructor
from ..models import InstructorReview, StudentReview, InstructorInfo
from ..serializers import (
    InstructorReviewSerializer,
    StudentReviewSerializer,
    InstructorReviewWriteSerializer,
    StudentReviewWriteSerializer,
    InstructorInfoWriteSerializer,
    InstructorInfoSerializer,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# 1) 강사 리뷰 ViewSet
# ════════════════════════════════════════════════════════════════════

class InstructorReviewViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    """
    URL: /tutoring/reviews/instructor/
    URL: /tutoring/reviews/instructor/<pk>/

    학생이 강사에 대한 별점과 후기를 관리하는 API ViewSet입니다.

    Request (POST /):
        instructor_id (int): 리뷰를 남길 강사의 ID.
        rating (int): 별점 (1~5).
        content (str): 후기 내용.

    Response (POST /):
        HTTP 201 Created:
        {
            "id": 1,
            "instructor": 5,
            "student": 9,
            "rating": 5,
            "content": "정말 잘 가르치십니다!",
            "created_at": "2026-04-26T06:51:26Z"
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorReviewWriteSerializer

    def get_queryset(self):
        # 본인(학생)이 작성한 리뷰만 수정/삭제 가능하도록 필터링
        return InstructorReview.objects.filter(student__user=self.request.user)

    def perform_create(self, serializer):
        """
        강사 리뷰 작성 시 현재 유저의 Student 프로필을 자동으로 연결합니다.
        학생 계정이 없는 유저(강사 전용 계정 등)는 PermissionDenied로 차단합니다.
        """
        try:
            student = Student.objects.get(user=self.request.user)
        except Student.DoesNotExist:
            logger.warning(
                "[REVIEW] 강사 리뷰 작성 실패 — 학생 프로필 없음. user_id=%s",
                self.request.user.pk
            )
            raise PermissionDenied("학생 계정만 강사 리뷰를 작성할 수 있습니다.")

        serializer.save(student=student)
        logger.info(
            "[REVIEW] 강사 리뷰 작성 완료. student_id=%s, review_id=%s",
            student.pk, serializer.instance.pk
        )


# ════════════════════════════════════════════════════════════════════
# 2) 학생 리뷰 ViewSet
# ════════════════════════════════════════════════════════════════════

class StudentReviewViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    """
    URL: /tutoring/reviews/student/
    URL: /tutoring/reviews/student/<pk>/

    강사가 학생에 대한 별점과 후기를 관리하는 API ViewSet입니다.

    Request (POST /):
        student_id (int): 리뷰를 남길 학생의 ID.
        rating (int): 별점 (1~5).
        content (str): 후기 내용.

    Response (POST /):
        HTTP 201 Created:
        {
            "id": 1,
            "student": 9,
            "instructor": 5,
            "rating": 4,
            "content": "수업 태도가 아주 좋습니다.",
            "created_at": "2026-04-26T06:51:26Z"
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentReviewWriteSerializer

    def get_queryset(self):
        # 본인(강사)이 작성한 리뷰만 수정/삭제 가능하도록 필터링
        return StudentReview.objects.filter(instructor__user=self.request.user)

    def perform_create(self, serializer):
        """
        학생 리뷰 작성 시 현재 유저의 Instructor 프로필을 자동으로 연결합니다.
        강사 계정이 없는 유저(학생 전용 계정 등)는 PermissionDenied로 차단합니다.
        """
        try:
            instructor = Instructor.objects.get(user=self.request.user)
        except Instructor.DoesNotExist:
            logger.warning(
                "[REVIEW] 학생 리뷰 작성 실패 — 강사 프로필 없음. user_id=%s",
                self.request.user.pk
            )
            raise PermissionDenied("강사 계정만 학생 리뷰를 작성할 수 있습니다.")

        serializer.save(instructor=instructor)
        logger.info(
            "[REVIEW] 학생 리뷰 작성 완료. instructor_id=%s, review_id=%s",
            instructor.pk, serializer.instance.pk
        )


# ════════════════════════════════════════════════════════════════════
# 3) 특정 학생에 대한 리뷰 목록 조회
# ════════════════════════════════════════════════════════════════════

class StudentReviewListAPIView(generics.ListAPIView):
    """
    URL: /tutoring/students/<student_id>/reviews/

    특정 학생이 여러 강사들로부터 받은 '학생 리뷰(StudentReview)' 목록을 조회하는 API View입니다.

    과외 성사 전 강사가 학생의 성향이나 이전 평가를 참고할 수 있도록 제공되는 정보입니다.

    Path Parameters:
        student_id (int): 평가를 받은 학생의 ID.

    Returns:
        List[StudentReviewSerializer]: 해당 학생에 대한 리뷰 리스트 (강사 프로필 등 포함).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentReviewSerializer

    def get_queryset(self):
        student_id = self.kwargs["student_id"]
        # 강사 정보와 과목을 미리 로드하여 N+1 쿼리 방지
        qs = StudentReview.objects.filter(student_id=student_id)
        
        if self.request.user.is_authenticated:
            blocked_user_ids = get_blocked_user_ids(self.request.user)
            if blocked_user_ids:
                qs = qs.exclude(instructor__user_id__in=blocked_user_ids)
                
        return qs.select_related(
            "instructor", "instructor__user"
        ).prefetch_related(
            "instructor__subjects"
        ).order_by("-id")


# ════════════════════════════════════════════════════════════════════
# 4) 강사 과외 정보 ViewSet (InstructorInfo CRUD)
# ════════════════════════════════════════════════════════════════════

class InstructorInfoViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    """
    URL: /tutoring/instructor-info/
    URL: /tutoring/instructor-info/<pk>/
    URL: /tutoring/instructor-info/mine/

    강사가 자신의 상세 '과외 소개 정보(InstructorInfo)'를 작성 및 관리하는 API ViewSet입니다.

    1명의 강사는 단 1개의 상세 정보(InstructorInfo) 객체만 가질 수 있습니다(1:1 관계).
    작성 시 이미 존재하는 경우 덮어쓰기(Update) 방식으로 동작하며,
    본인의 과외 소개 정보만을 관리(수정/삭제)할 수 있습니다.

    Actions:
        create: 상세 과외 정보 작성(또는 기존 정보 수정).
        retrieve: 과외 정보 상세 조회.
        partial_update: 과외 정보 일부 내용만 수정 (PATCH).
        destroy: 작성한 과외 정보 삭제.
        mine (GET): 본인(현재 로그인 강사)의 과외 정보 요약 조회용 커스텀 액션.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorInfoWriteSerializer

    def get_queryset(self):
        # 본인 강사 프로필에 연결된 정보만 접근 가능하도록 필터링
        return InstructorInfo.objects.filter(
            instructor__user=self.request.user
        ).select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects", "regions")

    def perform_create(self, serializer):
        """
        강사 과외 정보를 등록합니다.
        - 이미 InstructorInfo가 존재하면 해당 인스턴스를 업데이트합니다.
        - 존재하지 않으면 새로 생성합니다.
        - filter().first() 패턴으로 exists()+get() 2회 쿼리를 1회로 최적화합니다.
        """
        instructor = get_object_or_404(Instructor, user=self.request.user)

        # filter().first()는 없을 때 None을 반환하므로 exists()+get() 조합보다 안전하고 효율적
        instance = InstructorInfo.objects.filter(instructor=instructor).first()
        if instance:
            logger.info(
                "[INSTRUCTOR_INFO] 기존 과외 정보 업데이트. instructor_id=%s, info_id=%s",
                instructor.pk, instance.pk
            )
            serializer.update(instance, serializer.validated_data)
        else:
            serializer.save(instructor=instructor)
            logger.info(
                "[INSTRUCTOR_INFO] 새 과외 정보 생성. instructor_id=%s, info_id=%s",
                instructor.pk, serializer.instance.pk
            )

    @action(detail=False, methods=['get'], url_path='mine')
    def mine(self, request):
        """
        현재 로그인된 강사의 과외 정보를 조회합니다.
        InstructorInfo가 없으면 204 No Content를 반환합니다.

        URL: GET /tutoring/instructor-info/mine/
        """
        try:
            instructor = get_object_or_404(Instructor, user=request.user)
            info = InstructorInfo.objects.get(instructor=instructor)
            serializer = InstructorInfoSerializer(info)
            logger.debug(
                "[INSTRUCTOR_INFO] mine 조회 성공. instructor_id=%s", instructor.pk
            )
            return Response(serializer.data)
        except InstructorInfo.DoesNotExist:
            logger.debug(
                "[INSTRUCTOR_INFO] mine 조회 — 등록된 과외 정보 없음. user_id=%s",
                request.user.pk
            )
            return Response(None, status=status.HTTP_204_NO_CONTENT)

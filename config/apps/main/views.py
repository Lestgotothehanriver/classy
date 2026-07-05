from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)

from config.apps.accounts.models import Instructor, Student
from config.apps.cash.models import InstructorMonthlyRank, LectureRentalHistory
from config.apps.main.serializers import StudentMainTutorSerializer, InstructorMainStudentSerializer

# ════════════════════════════════════════════════════════════════════════════════
# 메인 화면 관련 View
# ════════════════════════════════════════════════════════════════════════════════

class StudentMainAPIView(APIView):
    """
    URL: /main/student/

    학생 메인 화면 정보를 제공합니다.
    내 지역 기반의 추천 강사 목록을 포함합니다.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.debug("[BACKEND_DEBUG_MAIN] StudentMain - user: %s", request.user.pk)
        user = request.user

        broad_region = user.region

        # 해당 대규모 지역으로 필터링 예: 서울 강남구 -> 서울로 시작하는 지역들만 필터링
        if broad_region:
            broad_region = broad_region.split(' ')[0]
            queryset = Instructor.objects.filter(user__region__startswith=broad_region)
        else:
            queryset = Instructor.objects.all()

        from django.db.models import Exists, OuterRef, Value, BooleanField, Count
        from config.apps.accounts.models import InstructorLike

        if hasattr(user, 'student_profile'):
            student = user.student_profile
            queryset = queryset.annotate(
                like_count=Count('liked_by', distinct=True),
                is_liked=Exists(
                    InstructorLike.objects.filter(
                        student=student,
                        instructor=OuterRef('pk')
                    )
                )
            )
        else:
            queryset = queryset.annotate(
                like_count=Count('liked_by', distinct=True),
                is_liked=Value(False, output_field=BooleanField())
            )

        # 랜덤 3명
        recommended_tutors = queryset.order_by('?')[:3]

        serializer = StudentMainTutorSerializer(recommended_tutors, many=True)
        logger.debug("[BACKEND_DEBUG_MAIN] StudentMain SUCCESS - tutors count: %d", len(serializer.data))
        return Response(serializer.data)


class InstructorMainAPIView(APIView):
    """
    URL: /main/instructor/

    강사 메인 화면 정보를 제공합니다.
    월간 순위, 이번 달 수익, 지역 기반 추천 학생 목록을 포함합니다.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.debug("[BACKEND_DEBUG_MAIN] InstructorMain - user: %s", request.user.pk)
        user = request.user
        
        try:
            instructor = user.instructor_profile
        except ObjectDoesNotExist:
            return Response({"detail": "Instructor profile is required."}, status=403)

        now = timezone.now()
        this_month = now.month
        this_year = now.year

        last_month = this_month - 1
        last_year = this_year
        if last_month == 0:
            last_month = 12
            last_year -= 1

        # 저번 달 순위 모델 조회
        rank_obj = InstructorMonthlyRank.objects.filter(
            instructor=instructor,
            year=last_year,
            month=last_month
        ).first()

        rank_data = None
        if rank_obj:
            rank_data = {
                "rank": rank_obj.rank,
                "total_cash": rank_obj.total_cash,
                "year": rank_obj.year,
                "month": rank_obj.month
            }

        # 이번 달 총 캐시 계산
        this_month_cash = LectureRentalHistory.objects.filter(
            lecture__instructor=instructor,
            created_at__year=this_year,
            created_at__month=this_month,
            is_canceled=False
        ).aggregate(
            total=Coalesce(Sum('purchased_cash'), 0)
        )['total']
        
        # 지역 맞춤 학생 3명 조회
        broad_region = user.region
        queryset = Student.objects.filter(tutoring_posts__is_active=True)
        if broad_region:
            broad_region = broad_region.split(' ')[0]
            queryset = queryset.filter(user__region__startswith=broad_region)
        recommended_students = queryset.distinct().order_by('?')[:3]
            
        recommended_students = queryset.order_by('?')[:3]
        student_serializer = InstructorMainStudentSerializer(recommended_students, many=True)
        logger.debug("[BACKEND_DEBUG_MAIN] InstructorMain SUCCESS - students count: %d", len(student_serializer.data))

        return Response({
            "previous_month_rank_info": rank_data,
            "this_month_total_cash": this_month_cash,
            "recommended_students": student_serializer.data
        })


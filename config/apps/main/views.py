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

    학생용 메인 대시보드 화면 데이터를 제공하는 API View입니다.

    GET 요청 시 로그인한 학생 유저 본인의 거주 지역을 기반으로, 과외 매칭 프로필을 가지고 있는 강사 중 동일 지역(예: 서울 강남구 → 서울 광역권) 소속의 추천 강사 3명을 무작위(랜덤)로 추출하여 반환하며 로그인한 학생이 해당 강사를 찜했는지 여부(is_liked) 및 누적 좋아요 개수를 계산하여 제공합니다.

    Returns:
        Response: List[StudentMainTutorSerializer] 데이터
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.debug("[BACKEND_DEBUG_MAIN] StudentMain - user: %s", request.user.pk)
        user = request.user

        broad_region = user.region

        queryset = Instructor.objects.filter(tutoring_profile__isnull=False)

        # 해당 대규모 지역으로 필터링 예: 서울 강남구 -> 서울로 시작하는 지역들만 필터링
        if broad_region:
            broad_region = broad_region.split(' ')[0]
            queryset = queryset.filter(user__region__startswith=broad_region)
    
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

    강사용 메인 대시보드 화면 데이터를 제공하는 API View입니다.

    GET 요청 시 강사 본인의 저번 달 정산 랭킹 정보(순위 및 합산액), 이번 달 VOD 판매로 획득한 누적 수익금 합계(this_month_total_cash), 그리고 강사 본인의 거주 지역과 매칭되는 활성화된 구인 공고를 올린 학생 3명을 무작위로 조회하여 요약 결과를 반환합니다.

    Returns:
        Response: {
            "previous_month_rank_info": dict | None,
            "this_month_total_cash": int,
            "recommended_students": List[InstructorMainStudentSerializer]
        }
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


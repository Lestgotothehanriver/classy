from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.core.exceptions import ObjectDoesNotExist

from config.apps.accounts.models import Instructor, Student
from config.apps.cash.models import InstructorMonthlyRank, LectureRentalHistory
from config.apps.main.serializers import StudentMainTutorSerializer, InstructorMainStudentSerializer

class StudentMainAPIView(APIView):
    """
    학생 메인 화면 API

    [URL]
    GET /main/student/

    [Request Body]
    (Empty)

    [Response]
    - 내 지역(대지역)과 동일/유사한 과외 선생님 랜덤 3명 추천 반환
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        broad_region = user.region

        # 해당 대규모 지역으로 필터링
        if broad_region:
            broad_region = broad_region.split(' ')[0]
            queryset = Instructor.objects.filter(user__region__startswith=broad_region)
        else:
            queryset = Instructor.objects.all()

        # 랜덤 3명
        recommended_tutors = queryset.order_by('?')[:3]

        serializer = StudentMainTutorSerializer(recommended_tutors, many=True)
        return Response(serializer.data)


class InstructorMainAPIView(APIView):
    """
    선생님 메인 화면 API

    [URL]
    GET /main/instructor/

    [Request Body]
    (Empty)

    [Response]
    - 저번 달의 월간 순위 및 이번 달의 예상 수익 반환
    - 내 지역(대지역)과 동일/유사한 학생 3명 추천 반환
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
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
        if broad_region:
            broad_region = broad_region.split(' ')[0]
            queryset = Student.objects.filter(user__region__startswith=broad_region)
        else:
            queryset = Student.objects.all()
            
        recommended_students = queryset.order_by('?')[:3]
        student_serializer = InstructorMainStudentSerializer(recommended_students, many=True)

        return Response({
            "previous_month_rank_info": rank_data,
            "this_month_total_cash": this_month_cash,
            "recommended_students": student_serializer.data
        })


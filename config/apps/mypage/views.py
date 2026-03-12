from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.db.models import Exists, OuterRef, Value, BooleanField, Count, Sum
from django.db.models.functions import Coalesce

from config.apps.lecture.models import Lecture
from config.apps.lecture.serializers import LectureListSerializer
from config.apps.cash.models import SettlementRecord, LectureRentalHistory

class StudentRentedLectureListView(generics.ListAPIView):
    """
    학생 본인이 대여한 동영상들을 조회하는 view
    GET /mypage/student/rented-lectures/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = LectureListSerializer

    def get_queryset(self):
        user = self.request.user
        student = getattr(user, 'student_profile', None)

        rented_lecture_ids = LectureRentalHistory.objects.filter(
            student=user, is_canceled=False
        ).values_list('lecture_id', flat=True).distinct()

        qs = Lecture.objects.filter(id__in=rented_lecture_ids, is_delete=False).select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects").annotate(
            like_count=Count("likes", distinct=True),
        ).order_by("-created_at")

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

        return qs

class StudentLikedLectureListView(generics.ListAPIView):
    """
    학생 본인이 추천/좋아요한 동영상들을 조회하는 view
    GET /mypage/student/liked-lectures/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = LectureListSerializer

    def get_queryset(self):
        user = self.request.user
        student = getattr(user, 'student_profile', None)
        
        if not student:
            return Lecture.objects.none()

        qs = Lecture.objects.filter(likes=student, is_delete=False).select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects").annotate(
            like_count=Count("likes", distinct=True),
        ).order_by("-created_at")

        qs = qs.annotate(
            is_liked=Value(True, output_field=BooleanField())
        )

        return qs

class InstructorUploadedLectureListView(generics.ListAPIView):
    """
    강사 본인이 업로드한 동영상들을 조회하는 view
    GET /mypage/instructor/uploaded-lectures/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = LectureListSerializer

    def get_queryset(self):
        user = self.request.user
        instructor = getattr(user, 'instructor_profile', None)
        
        if not instructor:
            return Lecture.objects.none()

        qs = Lecture.objects.filter(instructor=instructor, is_delete=False).select_related(
            "instructor", "instructor__user"
        ).prefetch_related("subjects").annotate(
            like_count=Count("likes", distinct=True),
        ).order_by("-created_at")
        
        qs = qs.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )

        return qs


class InstructorSettlementRequestView(APIView):
    """
    정산을 요청하는 view
    POST /mypage/instructor/request-settlement/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        instructor = getattr(user, 'instructor_profile', None)
        
        if not instructor:
            return Response({"detail": "Instructor profile is required."}, status=403)

        # 강사의 강의들 중 아직 정산되지 않은 렌탈 기록들 가져오기
        unsettled_rentals = LectureRentalHistory.objects.filter(
            lecture__instructor=instructor,
            is_canceled=False,
            is_settled=False
        )
        
        total_cash = unsettled_rentals.aggregate(
            total=Coalesce(Sum('purchased_cash'), 0)
        )['total']
        
        if total_cash == 0:
            return Response({"detail": "No settleable revenue found."}, status=400)
            
        settlement_record = SettlementRecord.objects.create(
            instructor=instructor,
            amount=total_cash,
            status='PENDING'
        )
        
        unsettled_rentals.update(is_settled=True)
        
        return Response({
            "detail": "Settlement requested successfully.",
            "settlement_id": settlement_record.id,
            "amount": total_cash,
            "status": settlement_record.status
        }, status=201)


class InstructorSettlementInfoView(APIView):
    """
    정산 정보를 반환하는 view
    GET /mypage/instructor/settlement-info/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        instructor = getattr(user, 'instructor_profile', None)
        
        if not instructor:
            return Response({"detail": "Instructor profile is required."}, status=403)

        total_revenue = LectureRentalHistory.objects.filter(
            lecture__instructor=instructor,
            is_canceled=False
        ).aggregate(
            total=Coalesce(Sum('purchased_cash'), 0)
        )['total']
        
        completed_revenue = SettlementRecord.objects.filter(
            instructor=instructor,
            status='COMPLETED'
        ).aggregate(
            total=Coalesce(Sum('amount'), 0)
        )['total']
        
        settleable_revenue = LectureRentalHistory.objects.filter(
            lecture__instructor=instructor,
            is_canceled=False,
            is_settled=False
        ).aggregate(
            total=Coalesce(Sum('purchased_cash'), 0)
        )['total']
        
        pending_revenue = SettlementRecord.objects.filter(
            instructor=instructor,
            status='PENDING'
        ).aggregate(
            total=Coalesce(Sum('amount'), 0)
        )['total']
        
        return Response({
            "total_revenue": total_revenue,
            "completed_revenue": completed_revenue,
            "settleable_revenue": settleable_revenue,
            "pending_revenue": pending_revenue
        })


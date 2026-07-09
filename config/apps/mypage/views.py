from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.db.models import Exists, OuterRef, Value, BooleanField, Count, Sum
from django.db.models.functions import Coalesce
import logging

logger = logging.getLogger(__name__)

from config.apps.lecture.models import Lecture
from config.apps.lecture.serializers import LectureListSerializer
from config.apps.cash.models import SettlementRecord, LectureRentalHistory, Account

class StudentRentedLectureListView(generics.ListAPIView):
    """
    URL: /mypage/student/rented-lectures/

    학생 본인이 대여 중인 VOD 강의 목록을 조회하는 API View입니다.

    GET 요청 시, 현재 로그인한 학생이 대여하고 아직 취소되지 않은 VOD 강의들의 전체 목록을 최신순으로 반환하며 찜 여부(is_liked)를 함께 반환합니다.

    Returns:
        Response: List[LectureListSerializer] 데이터
    """
    serializer_class = LectureListSerializer

    def get_queryset(self):
        """
        현재 로그인한 학생이 대여한 강의 쿼리셋을 반환합니다.

        Returns:
            QuerySet: 대여한 강의 객체 쿼리셋
        """
        logger.debug("[BACKEND_DEBUG_MYPAGE] StudentRentedLecture - user: %s", self.request.user.pk)
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
    URL: /mypage/student/liked-lectures/

    학생이 '찜(좋아요)'한 VOD 강의 목록을 조회하는 API View입니다.

    GET 요청 시, 현재 로그인한 학생 유저가 찜(좋아요) 처리한 동영상 강의 목록을 최신순 조회하며 is_liked=True로 마킹하여 반환합니다.

    Returns:
        Response: List[LectureListSerializer] 데이터
    """
    serializer_class = LectureListSerializer

    def get_queryset(self):
        """
        현재 로그인한 학생이 찜한 강의 쿼리셋을 반환합니다.

        Returns:
            QuerySet: 찜한 강의 객체 쿼리셋
        """
        logger.debug("[BACKEND_DEBUG_MYPAGE] StudentLikedLecture - user: %s", self.request.user.pk)
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
    URL: /mypage/instructor/uploaded-lectures/

    강사 본인이 직접 업로드한 VOD 동영상 강의 목록을 조회하는 API View입니다.

    GET 요청 시, 본인(강사)이 업로드한 전체 동영상 강의 중 삭제되지 않은 리스트를 최신순으로 조회하여 반환합니다.

    Returns:
        Response: List[LectureListSerializer] 데이터
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
    URL: /mypage/instructor/request-settlement/

    강사 본인의 판매 수익에 대한 정산 지급을 요청하는 API View입니다.

    POST 요청 시, 아직 정산 처리되지 않은(is_settled=False) 렌탈 결제 내역들을 합산하고 SettlementRecord를 PENDING 상태로 신규 생성하여 정산 신청을 처리합니다.

    Returns:
        Response: {
            "detail": "Settlement requested successfully.",
            "settlement_id": int,
            "amount": int,
            "status": "PENDING"
        } (HTTP 201 Created)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.debug("[BACKEND_DEBUG_MYPAGE] SettlementRequest - user: %s", request.user.pk)
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
        
        logger.debug("[BACKEND_DEBUG_MYPAGE] SettlementRequest SUCCESS - amount: %d", total_cash)
        return Response({
            "detail": "Settlement requested successfully.",
            "settlement_id": settlement_record.id,
            "amount": total_cash,
            "status": settlement_record.status
        }, status=201)


class InstructorSettlementInfoView(APIView):
    """
    URL: /mypage/instructor/settlement-info/

    강사의 누적 수익 및 정산 계좌 정보 등의 요약을 조회하는 API View입니다.

    GET 요청 시, 강사 계정의 총 누적 수익(total_revenue), 완료된 정산액(completed_revenue), 대기 상태 금액(pending_revenue), 정산 가능액(settleable_revenue) 및 연동된 정산 계좌 정보(account_info)를 조회하여 반환합니다.

    Returns:
        Response: {
            "total_revenue": int,
            "completed_revenue": int,
            "settleable_revenue": int,
            "pending_revenue": int,
            "account_info": dict | None
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.debug("[BACKEND_DEBUG_InstructorSettlementInfoView] SettlementInfo - user: %s", request.user.pk)
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
        
        account_info = None
        try:
            acct = instructor.account
            account_info = {
                'bank': acct.bank,
                'account_number': acct.account_number,
                'account_holder': acct.account_holder,
            }
        except Account.DoesNotExist:
            pass

        return Response({
            "total_revenue": total_revenue,
            "completed_revenue": completed_revenue,
            "settleable_revenue": settleable_revenue,
            "pending_revenue": pending_revenue,
            "account_info": account_info,
        })


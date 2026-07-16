from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.db import transaction
from django.db.models import Exists, OuterRef, Value, BooleanField, Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
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

        Query Parameters:
            status (str, optional): 'active'(기본) → 현재 대여중(만료 전),
                                    'expired' → 대여 기간이 만료된 강의.

        대여 만료일(expiration_date)은 대여 시점에 확정 저장되므로, 이를 기준으로
        각 강의를 active/expired로 분리한다.
        (같은 강의를 여러 번 대여한 경우, 하나라도 유효하면 active로 본다.)

        Returns:
            QuerySet: 대여한 강의 객체 쿼리셋
        """
        logger.debug("[BACKEND_DEBUG_MYPAGE] StudentRentedLecture - user: %s", self.request.user.pk)
        user = self.request.user
        student = getattr(user, 'student_profile', None)

        status = self.request.query_params.get('status', 'active')
        now = timezone.now()

        rentals = LectureRentalHistory.objects.filter(student=user, is_canceled=False)

        # 유효 대여가 하나라도 있는 강의 = '대여 중'
        active_ids = set(
            rentals.filter(expiration_date__gt=now).values_list('lecture_id', flat=True)
        )
        if status == 'expired':
            # 만료 대여가 있으나 유효 대여는 없는 강의 = '만료됨'
            expired_ids = set(
                rentals.filter(expiration_date__lte=now)
                .exclude(lecture_id__in=active_ids)
                .values_list('lecture_id', flat=True)
            )
            target_ids = expired_ids
        else:
            target_ids = active_ids

        qs = Lecture.objects.filter(id__in=target_ids, is_delete=False).select_related(
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

        # 동시성 보호: 대상 대여 row를 select_for_update로 잠근 뒤,
        # 잠금 안에서 합계를 다시 계산하고 정산 건에 귀속시킨다.
        # 이렇게 하면 중복 클릭/동시 요청이 직렬화되어 같은 대여가
        # 두 정산 건에 이중으로 들어가지 않는다.
        # 주의: aggregate()는 별도 쿼리라 FOR UPDATE 잠금이 걸리지 않으므로,
        #      values_list로 먼저 row를 materialize해 실제로 잠근 뒤 파이썬에서 합산한다.
        with transaction.atomic():
            locked_rentals = list(
                LectureRentalHistory.objects.select_for_update().filter(
                    lecture__instructor=instructor,
                    is_canceled=False,
                    is_settled=False,
                    purchased_cash__gt=0,  # 무료/0캐시 대여는 정산 대상에서 제외
                ).values_list('id', 'purchased_cash')
            )

            total_cash = sum(cash for _, cash in locked_rentals)

            if total_cash == 0:
                return Response({"detail": "No settleable revenue found."}, status=400)

            settlement_record = SettlementRecord.objects.create(
                instructor=instructor,
                amount=total_cash,
                status='PENDING'
            )

            # is_settled 마킹과 정산 건 FK 연결을 함께 기록해 감사 추적을 남긴다.
            rental_ids = [rental_id for rental_id, _ in locked_rentals]
            LectureRentalHistory.objects.filter(id__in=rental_ids).update(
                is_settled=True, settlement=settlement_record
            )

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


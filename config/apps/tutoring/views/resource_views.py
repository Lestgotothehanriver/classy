from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
import logging
from config.apps.block.utils import get_blocked_user_ids

from ..models import TutoringResource, TutoringResourceFile
from ..serializers import TutoringResourceSerializer, TutoringResourceListSerializer



logger = logging.getLogger(__name__)

class IsResourceParticipant(permissions.BasePermission):
    """
    과외 계약(TutoringResource) 리소스에 대한 접근 권한을 확인하는 클래스입니다.

    요청을 보낸 사용자(request.user)가 해당 리소스에 연결된 학생(student) 
    혹은 강사(instructor) 본인일 경우에만 True를 반환합니다.
    """
    def has_object_permission(self, request, view, obj):
        return request.user == obj.student.user or request.user == obj.instructor.user

class TutoringResourceViewSet(viewsets.ModelViewSet):
    """
    URL: /tutoring/resources/
    URL: /tutoring/resources/<pk>/
    URL: /tutoring/resources/<pk>/confirm-payment/

    과외 수업 관련 계약, 수업료 지불 상태 및 증빙 파일을 관리하는 API ViewSet입니다.

    GET /tutoring/resources/ 요청 시, 본인이 학생이나 강사로 속해 있는 전체 과외 계약 리소스 목록을 조회합니다. 차단된 유저의 계약은 배제됩니다.
    POST /tutoring/resources/ 요청 시, 입금 증빙 파일(fee_confirmation_file) 등을 첨부하여 새로운 과외 계약 정보를 생성합니다.
    GET /tutoring/resources/<pk>/ 요청 시, 특정 과외 계약 리소스의 상세 내역을 조회합니다.
    POST /tutoring/resources/<pk>/confirm-payment/ 요청 시, 강사가 직접 입금을 확인하고 상태를 AWAITING_CONFIRMATION으로 갱신 처리합니다.

    Path Parameters:
        pk (int): 대상 과외 계약(TutoringResource) ID.

    Request Body (POST /tutoring/resources/):
        student (int): 학생 ID (필수).
        instructor (int): 강사 ID (필수).
        fee_amount (int): 과외 수업료 금액 (필수).
        fee_confirmation_file (File, optional): 입금 증빙 파일 (다중 파일 가능).

    Returns:
        Response (GET /tutoring/resources/): List[TutoringResourceListSerializer] 데이터
        Response (POST /tutoring/resources/): TutoringResourceSerializer 데이터 (HTTP 201 Created)
        Response (GET /tutoring/resources/<pk>/): TutoringResourceSerializer 데이터
        Response (POST /tutoring/resources/<pk>/confirm-payment/): {
            "fee_payment_status": str
        }
    """
    permission_classes = [permissions.IsAuthenticated, IsResourceParticipant]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return TutoringResourceListSerializer
        return TutoringResourceSerializer

    def get_queryset(self):
        """
        요청한 사용자가 속한 과외 계약 목록만 필터링하여 반환합니다.
        
        Returns:
            QuerySet: 학생 본인 혹은 강사 본인으로 등록된 TutoringResource 쿼리셋.
        """
        user = self.request.user
        qs = TutoringResource.objects.all()

        if self.action == 'list':
            qs = qs.filter(Q(student__user=user) | Q(instructor__user=user))
            blocked_user_ids = get_blocked_user_ids(user)
            if blocked_user_ids:
                qs = qs.exclude(
                    Q(student__user_id__in=blocked_user_ids) |
                    Q(instructor__user_id__in=blocked_user_ids)
                )
            return qs

        return qs

    def perform_create(self, serializer):
        """
        새로운 과외 계약을 생성할 때 호출되는 Hook 메서드입니다.
        
        보안(IDOR 예방): 악의적인 사용자가 타인의 ID를 파라미터로 넘겨 
        대리 계약을 생성하는 것을 막기 위해 검증 로직을 포함합니다.
        
        Args:
            serializer (Serializer): 검증이 완료된 요청 데이터.
            
        Raises:
            PermissionDenied: 요청자(request.user)가 파라미터에 명시된 
                              학생이나 강사와 일치하지 않을 경우 발생.
        """
        # 1. 생성 시 넘겨받은 데이터(student, instructor) 검증
        # 악의적인 유저가 남의 ID로 리소스(계약)를 생성하는 것을 차단
        student = serializer.validated_data.get('student')
        instructor = serializer.validated_data.get('instructor')
        
        user = self.request.user
        is_student_match = (student and student.user == user)
        is_instructor_match = (instructor and instructor.user == user)
        
        if not (is_student_match or is_instructor_match):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("본인이 포함된 과외 계약만 생성할 수 있습니다.")

        resource = serializer.save()
        files = self.request.FILES.getlist('fee_confirmation_file')
        for f in files:
            TutoringResourceFile.objects.create(tutoring_resource=resource, file=f)

    @action(detail=True, methods=['post'], url_path='confirm-payment')
    def confirm_payment(self, request, pk=None):
        """
        강사가 입금 확인을 요청하여 상태를 업데이트합니다.

        이 액션은 강사 본인만 호출할 수 있으며, 호출 시 'fee_payment_status'가 
        'AWAITING_CONFIRMATION'으로 변경되어 학생에게 알림이 갈 수 있는 상태가 됩니다.

        Path Parameters:
            pk (int): 대상 TutoringResource의 ID.

        Response:
            HTTP 200 OK:
            {
                "fee_payment_status": "AWAITING_CONFIRMATION"
            }
            HTTP 403 Forbidden: 강사 본인이 아닌 경우.
            HTTP 404 Not Found: 리소스가 존재하지 않는 경우.
        """
        from django.db import transaction
        with transaction.atomic():
            try:
                resource = TutoringResource.objects.select_for_update().get(pk=pk)
            except TutoringResource.DoesNotExist:
                return Response({"error": "리소스를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

            if resource.instructor.user != request.user:
                return Response({"error": "강사 본인만 입금 확인을 요청할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

            resource.fee_payment_status = 'AWAITING_CONFIRMATION'
            resource.save(update_fields=['fee_payment_status'])

        return Response({'fee_payment_status': resource.fee_payment_status}, status=status.HTTP_200_OK)

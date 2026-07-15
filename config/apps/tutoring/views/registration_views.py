from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import CommissionInvoice, TutoringRegistration, TutoringSubmission
from ..registration_serializers import MyRegistrationInputSerializer
from ..registration_services import (
    RegistrationPermissionError,
    get_chat_room_for_user,
    save_my_registration,
    serialize_payment,
    serialize_registration,
)


class ChatRoomTutoringRegistrationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, chat_room_id):
        try:
            room, role = get_chat_room_for_user(chat_room_id, request.user)
        except RegistrationPermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        if room is None:
            return Response(
                {"detail": "채팅방을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        registration = (
            TutoringRegistration.objects.select_related(
                "student", "instructor", "resource"
            )
            .prefetch_related("submissions", "commission_invoices")
            .filter(chat_room=room)
            .first()
        )
        if registration is None:
            return Response(
                {
                    "registrationId": None,
                    "resourceId": None,
                    "chatRoomId": room.pk,
                    "subject": None,
                    "startDate": None,
                    "student": {
                        "id": room.student.user_id,
                        "userName": room.student.user.user_name,
                    },
                    "instructor": {
                        "id": room.instructor.user_id,
                        "userName": room.instructor.user.user_name,
                    },
                    "attributeValidationStatus": "UNCHECKED",
                    "contractStatus": "COLLECTING",
                    "studentSubmitted": False,
                    "instructorSubmitted": False,
                    "mySubmission": None,
                    "counterpartySubmission": {"submitted": False},
                    "payment": None,
                }
            )

        invoice = registration.commission_invoices.filter(
            invoice_type=CommissionInvoice.InvoiceType.INITIAL
        ).first()
        data = serialize_registration(registration, request.user, role)
        data["payment"] = serialize_payment(invoice)
        return Response(data)


class MyTutoringRegistrationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def put(self, request, chat_room_id):
        try:
            room, role = get_chat_room_for_user(chat_room_id, request.user)
        except RegistrationPermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        if room is None:
            return Response(
                {"detail": "채팅방을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        proof_files = request.FILES.getlist("feeConfirmationFiles")
        if not proof_files:
            proof_files = request.FILES.getlist("fee_confirmation_file")
        if role == TutoringSubmission.Role.INSTRUCTOR and not proof_files:
            raise ValidationError(
                {"feeConfirmationFiles": "입금 증빙 파일을 한 개 이상 첨부해 주세요."}
            )
        if role == TutoringSubmission.Role.STUDENT and proof_files:
            raise ValidationError(
                {"feeConfirmationFiles": "학생 등록에는 입금 증빙을 첨부하지 않습니다."}
            )

        serializer = MyRegistrationInputSerializer(
            data=request.data,
            context={"role": role},
        )
        serializer.is_valid(raise_exception=True)
        result = save_my_registration(
            chat_room_id,
            request.user,
            serializer.validated_data,
            proof_files=proof_files,
        )
        if result is None:
            return Response(
                {"detail": "채팅방을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "registration": serialize_registration(
                    result["registration"],
                    request.user,
                    result["role"],
                    result["mismatched_fields"],
                ),
                "payment": serialize_payment(result["invoice"]),
            }
        )


class CommissionPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, registration_id):
        registration = (
            TutoringRegistration.objects.filter(pk=registration_id)
            .filter(Q(student=request.user) | Q(instructor=request.user))
            .first()
        )
        if registration is None:
            return Response(
                {"detail": "과외 등록을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        invoice = registration.commission_invoices.order_by(
            "-created_at", "-pk"
        ).first()
        if invoice is None:
            return Response(
                {"detail": "수수료 입금 정보가 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serialize_payment(invoice))

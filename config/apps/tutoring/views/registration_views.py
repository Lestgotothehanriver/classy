from django.db import transaction
from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import CommissionInvoice, TutoringRegistration, VirtualAccountPayment
from ..registration_serializers import MyRegistrationInputSerializer
from ..registration_services import (
    RegistrationPermissionError,
    VirtualAccountIssueError,
    create_reissue_payment,
    get_chat_room_for_user,
    issue_virtual_account,
    latest_commission_payment,
    latest_initial_payment,
    mark_issue_failed,
    refresh_expiration,
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

        registration = TutoringRegistration.objects.select_related(
            "student", "instructor"
        ).prefetch_related("submissions").filter(chat_room=room).first()
        if registration is None:
            return Response(
                {
                    "registrationId": None,
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
                    "studentSubmitted": False,
                    "instructorSubmitted": False,
                    "mySubmission": None,
                    "counterpartySubmission": {"submitted": False},
                }
            )
        return Response(serialize_registration(registration, request.user, role))


class MyTutoringRegistrationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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

        serializer = MyRegistrationInputSerializer(
            data=request.data, context={"role": role}
        )
        serializer.is_valid(raise_exception=True)
        result = save_my_registration(
            chat_room_id, request.user, serializer.validated_data
        )
        if result is None:
            return Response(
                {"detail": "채팅방을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payment_error = None
        payment = result["payment_to_issue"]
        if payment is not None:
            try:
                payment = issue_virtual_account(payment, request.user.user_name)
            except VirtualAccountIssueError as exc:
                mark_issue_failed(payment, exc)
                payment_error = str(exc)
        else:
            payment = latest_initial_payment(result["registration"])

        response_data = {
            "registration": serialize_registration(
                result["registration"],
                request.user,
                result["role"],
                result["mismatched_fields"],
            ),
            "payment": serialize_payment(payment, due_key="dueDate"),
        }
        if payment_error:
            response_data["paymentError"] = payment_error
        return Response(response_data)


class CommissionPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _registration(self, registration_id, user):
        return TutoringRegistration.objects.filter(pk=registration_id).filter(
            Q(student=user) | Q(instructor=user)
        ).first()

    def get(self, request, registration_id):
        registration = self._registration(registration_id, request.user)
        if registration is None:
            return Response(
                {"detail": "과외 등록을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        payment = latest_commission_payment(registration)
        if payment is None:
            return Response(
                {"detail": "수수료 결제 정보가 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serialize_payment(payment))


class CommissionPaymentReissueView(CommissionPaymentView):
    def post(self, request, registration_id):
        with transaction.atomic():
            registration = TutoringRegistration.objects.select_for_update().filter(
                pk=registration_id, instructor=request.user
            ).first()
            if registration is None:
                return Response(
                    {"detail": "강사 본인만 가상계좌를 재발급할 수 있습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            invoice = CommissionInvoice.objects.select_for_update().filter(
                registration=registration
            ).order_by("-created_at", "-pk").first()
            if invoice is None:
                return Response(
                    {"detail": "수수료 청구서가 없습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            latest = invoice.virtual_account_payments.order_by("-created_at", "-pk").first()
            refresh_expiration(latest)
            if latest and latest.fee_payment_status not in {
                VirtualAccountPayment.FeePaymentStatus.FAILED,
                VirtualAccountPayment.FeePaymentStatus.EXPIRED,
                VirtualAccountPayment.FeePaymentStatus.CANCELLED,
            }:
                return Response(
                    {"detail": "실패하거나 만료된 가상계좌만 재발급할 수 있습니다."},
                    status=status.HTTP_409_CONFLICT,
                )
            payment = create_reissue_payment(invoice)
            invoice.status = CommissionInvoice.Status.READY
            invoice.save(update_fields=["status", "updated_at"])

        try:
            payment = issue_virtual_account(payment, request.user.user_name)
        except VirtualAccountIssueError as exc:
            mark_issue_failed(payment, exc)
            return Response(
                {"payment": serialize_payment(payment), "paymentError": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(serialize_payment(payment), status=status.HTTP_201_CREATED)

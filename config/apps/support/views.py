"""앱·사용자 웹이 공통으로 사용하는 티켓 API입니다."""

import mimetypes
import os

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.db.models import OuterRef, Subquery
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.tutoring.models import PaybackPayout, TutoringRegistration

from .models import SupportAttachment, SupportEvent, SupportTicket
from .serializers import SupportMessageCreateSerializer, SupportTicketCreateSerializer, SupportTicketSerializer
from .services import USER_EVENT_TYPES, add_user_message, mark_ticket_read, ticket_context


def _ticket_queryset():
    """목록 표시용 최근 실제 처리자를 함께 조회합니다."""
    operator_events = (
        SupportEvent.objects.filter(ticket_id=OuterRef("pk"), actor__isnull=False)
        .exclude(event_type__in=USER_EVENT_TYPES)
        .order_by("-created_at", "-pk")
    )
    return SupportTicket.objects.annotate(
        last_operator_name=Subquery(operator_events.values("actor_name")[:1]),
        last_operator_at=Subquery(operator_events.values("created_at")[:1]),
    )


class TicketListCreateView(APIView):
    """GET 목록과 POST 새 티켓 접수를 제공합니다."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        tickets = _ticket_queryset().filter(requester=request.user)
        return Response(SupportTicketSerializer(tickets, many=True).data)

    def post(self, request):
        serializer = SupportTicketCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        files = request.FILES.getlist("files")
        if len(files) > 5:
            return Response({"files": "첨부 파일은 최대 5개까지 등록할 수 있습니다."}, status=400)
        message = ticket.messages.first()
        for uploaded in files:
            SupportAttachment.objects.create(
                ticket=ticket,
                message=message,
                file=uploaded,
                original_name=uploaded.name,
            )
        return Response(SupportTicketSerializer(ticket, context={"detail": True}).data, status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    """본인 티켓의 공개 대화와 상태 이력을 반환합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        ticket = get_object_or_404(_ticket_queryset(), pk=pk, requester=request.user)
        return Response(SupportTicketSerializer(ticket, context={"detail": True}).data)


class TicketReadView(APIView):
    """요청자 본인의 운영자 답변을 읽음으로 처리합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        ticket = get_object_or_404(SupportTicket, pk=pk, requester=request.user)
        mark_ticket_read(ticket, user=request.user)
        return Response({"id": ticket.pk, "last_user_read_at": ticket.last_user_read_at})


class TicketContextView(APIView):
    """문의 접수 화면의 구매·성사등록·인증 선택값을 제공합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ticket_context(request.user))


class PaybackPayoutDetailView(APIView):
    """학생 본인의 성사등록 페이백 지급 현황을 제공합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, registration_id):
        registration = get_object_or_404(
            TutoringRegistration.objects.select_related("student"),
            pk=registration_id,
            student=request.user,
        )
        try:
            payout = registration.payback_payout
        except PaybackPayout.DoesNotExist:
            payout = None
        return Response(
            {
                "registration": {
                    "id": registration.pk,
                    "subject": registration.subject,
                    "contract_status": registration.contract_status,
                    "contract_status_label": registration.get_contract_status_display(),
                },
                "payout": None
                if payout is None
                else {
                    "id": payout.pk,
                    "amount": payout.amount,
                    "status": payout.status,
                    "status_label": payout.get_status_display(),
                    "processed_at": payout.processed_at,
                },
            }
        )


class TicketMessageView(APIView):
    """사용자 답변과 선택 첨부 파일을 등록합니다."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request, pk):
        ticket = get_object_or_404(SupportTicket, pk=pk, requester=request.user)
        serializer = SupportMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        files = request.FILES.getlist("files")
        if len(files) > 5:
            return Response({"files": "첨부 파일은 최대 5개까지 등록할 수 있습니다."}, status=400)
        message = add_user_message(ticket, user=request.user, content=serializer.validated_data["content"])
        for uploaded in files:
            SupportAttachment.objects.create(ticket=ticket, message=message, file=uploaded, original_name=uploaded.name)
        ticket.refresh_from_db()
        return Response(SupportTicketSerializer(ticket, context={"detail": True}).data)


class TicketAttachmentView(APIView):
    """요청자 본인만 보호 첨부를 열람합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, attachment_id):
        attachment = get_object_or_404(SupportAttachment, pk=attachment_id, ticket_id=pk, ticket__requester=request.user)
        try:
            handle = attachment.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Attachment missing") from exc
        return FileResponse(handle, as_attachment=False, filename=attachment.original_name or os.path.basename(attachment.file.name), content_type=mimetypes.guess_type(attachment.file.name)[0] or "application/octet-stream")

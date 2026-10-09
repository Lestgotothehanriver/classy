"""앱·사용자 웹이 공통으로 사용하는 티켓 API입니다."""

import mimetypes
import os

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SupportAttachment, SupportTicket
from .serializers import SupportMessageCreateSerializer, SupportTicketCreateSerializer, SupportTicketSerializer
from .services import add_user_message


class TicketListCreateView(APIView):
    """GET 목록과 POST 새 티켓 접수를 제공합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tickets = SupportTicket.objects.filter(requester=request.user).select_related("assigned_to")
        return Response(SupportTicketSerializer(tickets, many=True).data)

    def post(self, request):
        serializer = SupportTicketCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        return Response(SupportTicketSerializer(ticket, context={"detail": True}).data, status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    """본인 티켓의 공개 대화와 상태 이력을 반환합니다."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        ticket = get_object_or_404(SupportTicket.objects.select_related("assigned_to"), pk=pk, requester=request.user)
        return Response(SupportTicketSerializer(ticket, context={"detail": True}).data)


class TicketMessageView(APIView):
    """사용자 답변과 선택 첨부 파일을 등록합니다."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request, pk):
        ticket = get_object_or_404(SupportTicket, pk=pk, requester=request.user)
        serializer = SupportMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = add_user_message(ticket, user=request.user, content=serializer.validated_data["content"])
        for uploaded in request.FILES.getlist("files")[:5]:
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

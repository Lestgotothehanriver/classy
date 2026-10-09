"""슈퍼관리자 문의 티켓 운영 API입니다."""

import mimetypes
import os

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.adminops.models import AdminActionLog
from config.apps.notification.helpers import notify_support_ticket_update
from config.apps.support.models import SupportAttachment, SupportMessage, SupportTicket
from config.apps.support.services import add_event, display_name, transition

from ..permissions import IsSuperAdmin
from ..serializers.support import (
    AdminNameChangeSerializer,
    AdminSupportTicketSerializer,
    AdminTicketAssignSerializer,
    AdminTicketNoteSerializer,
    AdminTicketReplySerializer,
    AdminTicketStatusSerializer,
)


def _base_queryset():
    return SupportTicket.objects.select_related("requester", "assigned_to").prefetch_related("messages__attachments", "events")


def _request_id(request):
    return request.headers.get("X-Request-ID", "")


def _notify_requester(ticket, *, title: str, body: str) -> None:
    if ticket.requester_id:
        notify_support_ticket_update(
            ticket.requester,
            role=ticket.requester_role or "student",
            ticket_id=ticket.pk,
            title=title,
            body=body,
        )


class AdminSupportTicketListView(ListAPIView):
    """GET /admin-api/v1/inquiries/ - 운영 필터가 적용된 티켓 목록입니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = AdminSupportTicketSerializer

    def get_queryset(self):
        qs = _base_queryset()
        params = self.request.query_params
        if params.get("status") in SupportTicket.Status.values:
            qs = qs.filter(status=params["status"])
        if params.get("ticket_type") in SupportTicket.TicketType.values:
            qs = qs.filter(ticket_type=params["ticket_type"])
        if params.get("unassigned") == "true":
            qs = qs.filter(assigned_to__isnull=True)
        elif params.get("assignee_id", "").isdigit():
            qs = qs.filter(assigned_to_id=int(params["assignee_id"]))
        if params.get("q"):
            q = params["q"].strip()
            qs = qs.filter(Q(title__icontains=q) | Q(requester_name__icontains=q) | Q(requester__user_name__icontains=q))
        return qs.order_by("-updated_at", "-pk")


class AdminSupportTicketSummaryView(APIView):
    """운영 대시보드 및 목록 상단에 쓰는 상태별 문의 수입니다."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = SupportTicket.objects.values("status").annotate(count=Count("id"))
        counts = {row["status"]: row["count"] for row in rows}
        return Response({
            "received": counts.get(SupportTicket.Status.RECEIVED, 0),
            "unassigned": SupportTicket.objects.filter(assigned_to__isnull=True).exclude(status=SupportTicket.Status.CLOSED).count(),
            "in_progress": counts.get(SupportTicket.Status.IN_PROGRESS, 0),
            "waiting_for_user": counts.get(SupportTicket.Status.WAITING_FOR_USER, 0),
        })


class AdminSupportTicketDetailView(RetrieveAPIView):
    """티켓 공개 대화·내부 메모·감사 이력을 함께 반환합니다."""

    permission_classes = [IsSuperAdmin]
    serializer_class = AdminSupportTicketSerializer

    def get_queryset(self):
        return _base_queryset()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["detail"] = True
        return context


class AdminSupportTicketReplyView(APIView):
    """공개 답변을 등록하고, 필요하면 한 번의 알림으로 상태도 함께 전환합니다."""

    permission_classes = [IsSuperAdmin]

    @transaction.atomic
    def post(self, request, pk):
        serializer = AdminTicketReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = get_object_or_404(SupportTicket.objects.select_for_update(), pk=pk)
        if ticket.status == SupportTicket.Status.CLOSED:
            return Response({"error": "종결된 문의에는 답변할 수 없습니다."}, status=409)
        message = SupportMessage.objects.create(ticket=ticket, sender=request.user, sender_name=display_name(request.user), sender_kind=SupportMessage.SenderKind.ADMIN, content=serializer.validated_data["content"])
        ticket.last_admin_message_at = message.created_at
        ticket.save(update_fields=["last_admin_message_at", "updated_at"])
        next_status = serializer.validated_data.get("status")
        if next_status and next_status != ticket.status:
            transition(ticket, actor=request.user, status=next_status)
        add_event(ticket, actor=request.user, event_type="ticket.public_reply", payload={"message_id": message.pk})
        AdminActionLog.record(admin=request.user, action="support.reply", target_type="SupportTicket", target_id=ticket.pk, request_id=_request_id(request))
        _notify_requester(ticket, title="1:1 문의에 답변이 등록되었어요", body="내 문의에서 운영자 답변을 확인해 주세요.")
        return Response(AdminSupportTicketSerializer(_base_queryset().get(pk=pk), context={"detail": True}).data)


class AdminSupportTicketNoteView(APIView):
    """사용자에게 노출되지 않는 내부 메모를 남깁니다."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = AdminTicketNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = get_object_or_404(SupportTicket, pk=pk)
        message = SupportMessage.objects.create(ticket=ticket, sender=request.user, sender_name=display_name(request.user), sender_kind=SupportMessage.SenderKind.ADMIN, content=serializer.validated_data["content"], is_internal=True)
        add_event(ticket, actor=request.user, event_type="ticket.internal_note", payload={"message_id": message.pk})
        AdminActionLog.record(admin=request.user, action="support.internal_note", target_type="SupportTicket", target_id=ticket.pk, request_id=_request_id(request))
        return Response(AdminSupportTicketSerializer(_base_queryset().get(pk=pk), context={"detail": True}).data)


class AdminSupportTicketAssignView(APIView):
    """슈퍼관리자 담당자를 배정하거나 해제합니다."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = AdminTicketAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = get_object_or_404(SupportTicket, pk=pk)
        assignee_id = serializer.validated_data.get("assignee_id")
        assignee = None
        if assignee_id is not None:
            assignee = get_object_or_404(get_user_model().objects.filter(is_superuser=True, is_active=True), pk=assignee_id)
        before = ticket.assigned_to_id
        ticket.assigned_to = assignee
        ticket.save(update_fields=["assigned_to", "updated_at"])
        add_event(ticket, actor=request.user, event_type="ticket.assigned", payload={"from": before, "to": assignee_id})
        AdminActionLog.record(admin=request.user, action="support.assign", target_type="SupportTicket", target_id=ticket.pk, metadata={"from": before, "to": assignee_id}, request_id=_request_id(request))
        return Response(AdminSupportTicketSerializer(_base_queryset().get(pk=pk), context={"detail": True}).data)


class AdminSupportTicketStatusView(APIView):
    """운영자 상태 전이와 사용자 알림을 처리합니다."""

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):
        serializer = AdminTicketStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = get_object_or_404(SupportTicket, pk=pk)
        try:
            transition(ticket, actor=request.user, status=serializer.validated_data["status"], reason=serializer.validated_data.get("reason", ""))
        except Exception as exc:
            return Response({"error": str(exc.detail[0]) if hasattr(exc, "detail") else "상태를 변경할 수 없습니다."}, status=409)
        AdminActionLog.record(admin=request.user, action="support.status", target_type="SupportTicket", target_id=ticket.pk, reason=serializer.validated_data.get("reason", ""), metadata={"status": ticket.status}, request_id=_request_id(request))
        labels = {SupportTicket.Status.WAITING_FOR_USER: ("추가 정보가 필요해요", "내 문의에서 운영자 요청을 확인해 주세요."), SupportTicket.Status.RESOLVED: ("1:1 문의가 해결 처리되었어요", "내 문의에서 처리 내용을 확인해 주세요."), SupportTicket.Status.CLOSED: ("1:1 문의가 종결되었어요", "종결된 문의는 읽기 전용으로 보관됩니다.")}
        if ticket.status in labels:
            title, body = labels[ticket.status]
            _notify_requester(ticket, title=title, body=body)
        return Response(AdminSupportTicketSerializer(_base_queryset().get(pk=pk), context={"detail": True}).data)


class AdminSupportTicketApproveNameChangeView(APIView):
    """이름 변경 티켓에 한해 사용자 이름을 원자적으로 변경합니다."""

    permission_classes = [IsSuperAdmin]

    @transaction.atomic
    def post(self, request, pk):
        serializer = AdminNameChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = get_object_or_404(SupportTicket.objects.select_for_update().select_related("requester"), pk=pk)
        if ticket.ticket_type != SupportTicket.TicketType.NAME_CHANGE or ticket.requester is None:
            return Response({"error": "처리할 수 있는 이름 변경 요청이 아닙니다."}, status=400)
        user = get_user_model().objects.select_for_update().get(pk=ticket.requester_id)
        before = {"last_name": user.last_name, "first_name": user.first_name}
        user.last_name = ticket.requested_last_name
        user.first_name = ticket.requested_first_name
        user.save(update_fields=["last_name", "first_name"])
        add_event(ticket, actor=request.user, event_type="ticket.name_change_approved", payload={"before": before, "after": {"last_name": user.last_name, "first_name": user.first_name}, "reason": serializer.validated_data.get("reason", "")})
        AdminActionLog.record(admin=request.user, action="support.name_change_approve", target_type="SupportTicket", target_id=ticket.pk, reason=serializer.validated_data.get("reason", ""), metadata={"before": before, "after": {"last_name": user.last_name, "first_name": user.first_name}}, request_id=_request_id(request))
        _notify_requester(ticket, title="이름 변경이 승인되었어요", body="프로필에서 변경된 이름을 확인해 주세요.")
        return Response(AdminSupportTicketSerializer(_base_queryset().get(pk=pk), context={"detail": True}).data)


class AdminSupportTicketAttachmentView(APIView):
    """슈퍼관리자만 티켓 첨부를 보호 스트리밍으로 열람합니다."""

    permission_classes = [IsSuperAdmin]

    def get(self, request, pk, attachment_id):
        attachment = get_object_or_404(SupportAttachment, pk=attachment_id, ticket_id=pk)
        try:
            handle = attachment.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Attachment missing") from exc
        return FileResponse(handle, as_attachment=False, filename=attachment.original_name or os.path.basename(attachment.file.name), content_type=mimetypes.guess_type(attachment.file.name)[0] or "application/octet-stream")

"""슈퍼관리자 문의 티켓 운영 API입니다."""

import mimetypes
import os

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from config.apps.adminops.models import AdminActionLog
from config.apps.notification.helpers import notify_support_ticket_update
from config.apps.support.models import SupportAttachment, SupportEvent, SupportMessage, SupportTicket
from config.apps.support.services import USER_EVENT_TYPES, add_event, display_name, transition

from ..permissions import IsSuperAdmin
from ..serializers.support import (
    AdminNameChangeSerializer,
    AdminSupportTicketSerializer,
    AdminTicketNoteSerializer,
    AdminTicketReplySerializer,
    AdminTicketStatusSerializer,
)


def _base_queryset():
    operator_events = (
        SupportEvent.objects.filter(ticket_id=OuterRef("pk"), actor__isnull=False)
        .exclude(event_type__in=USER_EVENT_TYPES)
        .order_by("-created_at", "-pk")
    )
    return SupportTicket.objects.select_related("requester").prefetch_related("messages__attachments", "events").annotate(
        last_operator_name=Subquery(operator_events.values("actor_name")[:1]),
        last_operator_at=Subquery(operator_events.values("created_at")[:1]),
    )


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


def _status_notification(status: str) -> tuple[str, str] | None:
    """사용자 확인이 필요한 상태 전이의 단일 푸시 문구를 반환합니다."""
    messages = {
        SupportTicket.Status.WAITING_FOR_USER: (
            "추가 정보가 필요해요",
            "내 문의에서 운영자 요청을 확인해 주세요.",
        ),
        SupportTicket.Status.RESOLVED: (
            "1:1 문의가 해결 처리되었어요",
            "내 문의에서 처리 내용을 확인해 주세요.",
        ),
        SupportTicket.Status.CLOSED: (
            "1:1 문의가 종결되었어요",
            "종결된 문의는 읽기 전용으로 보관됩니다.",
        ),
    }
    return messages.get(status)


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
        if params.get("q"):
            q = params["q"].strip()
            qs = qs.filter(Q(title__icontains=q) | Q(requester_name__icontains=q) | Q(requester__user_name__icontains=q))
        if params.get("operator_q"):
            qs = qs.filter(events__actor_name__icontains=params["operator_q"].strip()).distinct()
        created_from = parse_date(params.get("created_from", ""))
        if created_from:
            qs = qs.filter(created_at__date__gte=created_from)
        created_to = parse_date(params.get("created_to", ""))
        if created_to:
            qs = qs.filter(created_at__date__lte=created_to)
        return qs.order_by("-updated_at", "-pk")


class AdminSupportTicketSummaryView(APIView):
    """운영 대시보드 및 목록 상단에 쓰는 상태별 문의 수입니다."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        rows = SupportTicket.objects.values("status").annotate(count=Count("id"))
        counts = {row["status"]: row["count"] for row in rows}
        return Response({
            "received": counts.get(SupportTicket.Status.RECEIVED, 0),
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
        status_notification = _status_notification(ticket.status)
        if status_notification:
            title, body = status_notification
        else:
            title, body = "1:1 문의에 답변이 등록되었어요", "내 문의에서 운영자 답변을 확인해 주세요."
        _notify_requester(ticket, title=title, body=body)
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
        status_notification = _status_notification(ticket.status)
        if status_notification:
            title, body = status_notification
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
        if ticket.status == SupportTicket.Status.CLOSED:
            return Response({"error": "종결된 문의는 처리할 수 없습니다."}, status=409)
        if ticket.events.filter(event_type="ticket.name_change_approved").exists():
            return Response({"error": "이미 승인된 이름 변경 요청입니다."}, status=409)
        user = get_user_model().objects.select_for_update().get(pk=ticket.requester_id)
        before = {"last_name": user.last_name, "first_name": user.first_name}
        user.last_name = ticket.requested_last_name
        user.first_name = ticket.requested_first_name
        user.save(update_fields=["last_name", "first_name"])
        add_event(ticket, actor=request.user, event_type="ticket.name_change_approved", payload={"before": before, "after": {"last_name": user.last_name, "first_name": user.first_name}, "reason": serializer.validated_data.get("reason", "")})
        if ticket.status == SupportTicket.Status.RECEIVED:
            transition(ticket, actor=request.user, status=SupportTicket.Status.IN_PROGRESS)
        if ticket.status in (SupportTicket.Status.IN_PROGRESS, SupportTicket.Status.WAITING_FOR_USER):
            transition(ticket, actor=request.user, status=SupportTicket.Status.RESOLVED)
        AdminActionLog.record(admin=request.user, action="support.name_change_approve", target_type="SupportTicket", target_id=ticket.pk, reason=serializer.validated_data.get("reason", ""), metadata={"before": before, "after": {"last_name": user.last_name, "first_name": user.first_name}}, request_id=_request_id(request))
        _notify_requester(ticket, title="이름 변경이 처리 완료되었어요", body="프로필에서 변경된 이름을 확인해 주세요.")
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

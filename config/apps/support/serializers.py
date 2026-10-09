"""사용자 티켓 API 직렬화기입니다."""

import os

from rest_framework import serializers

from .models import SupportAttachment, SupportEvent, SupportMessage, SupportTicket
from .services import related_summary, ticket_role, validate_related_target


TYPE_TITLES = {
    SupportTicket.TicketType.NAME_CHANGE: "이름 변경 요청",
    SupportTicket.TicketType.CASH_PAYMENT: "캐시·결제 문의",
    SupportTicket.TicketType.TUTORING_FEE: "성사 수수료 문의",
    SupportTicket.TicketType.PAYBACK: "페이백 문의",
    SupportTicket.TicketType.VERIFICATION_PROFILE: "인증·프로필 문의",
    SupportTicket.TicketType.LEGACY: "기존 문의",
}


class SupportAttachmentSerializer(serializers.ModelSerializer):
    """파일 URL 대신 보호 API 식별자만 반환합니다."""

    filename = serializers.SerializerMethodField()

    class Meta:
        model = SupportAttachment
        fields = ["id", "filename", "created_at"]

    def get_filename(self, obj):
        return obj.original_name or os.path.basename(obj.file.name)


class SupportMessageSerializer(serializers.ModelSerializer):
    """공개/내부 메시지를 렌더링합니다."""

    attachments = SupportAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = SupportMessage
        fields = ["id", "sender_name", "sender_kind", "content", "is_internal", "created_at", "attachments"]


class SupportEventSerializer(serializers.ModelSerializer):
    """사용자에게 공개 가능한 시스템 상태 이력입니다."""

    class Meta:
        model = SupportEvent
        fields = ["id", "event_type", "payload", "created_at"]


class SupportTicketSerializer(serializers.ModelSerializer):
    """사용자 티켓 목록·상세 표현입니다."""

    related = serializers.SerializerMethodField()
    unread_admin_replies = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id", "ticket_type", "status", "title", "requester_name", "requester_role",
            "assigned_to_name", "related_kind", "related_id", "related", "requested_last_name",
            "requested_first_name", "name_change_reason", "unread_admin_replies", "messages",
            "events", "created_at", "updated_at", "resolved_at", "closed_at",
        ]

    def get_related(self, obj):
        return related_summary(obj)

    def get_assigned_to_name(self, obj):
        return "" if obj.assigned_to is None else obj.assigned_to.user_name

    def get_unread_admin_replies(self, obj):
        latest_user = obj.last_user_message_at
        if obj.last_admin_message_at is None:
            return 0
        return int(latest_user is None or obj.last_admin_message_at > latest_user)

    def get_messages(self, obj):
        if not self.context.get("detail"):
            return []
        return SupportMessageSerializer(obj.messages.filter(is_internal=False), many=True).data

    def get_events(self, obj):
        if not self.context.get("detail"):
            return []
        events = obj.events.exclude(event_type__in=["ticket.internal_note"])
        return SupportEventSerializer(events, many=True).data


class SupportTicketCreateSerializer(serializers.Serializer):
    """유형별 필수 정보와 소유 관계를 검증해 티켓을 생성합니다."""

    ticket_type = serializers.ChoiceField(choices=SupportTicket.TicketType.choices)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    content = serializers.CharField()
    requester_role = serializers.ChoiceField(choices=["student", "instructor"], required=False)
    related_kind = serializers.ChoiceField(choices=SupportTicket.RelatedKind.choices, required=False, allow_blank=True)
    related_id = serializers.IntegerField(required=False, min_value=1)
    requested_last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    requested_first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    name_change_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        ticket_type = attrs["ticket_type"]
        if ticket_type == SupportTicket.TicketType.NAME_CHANGE:
            if not attrs.get("requested_last_name") or not attrs.get("requested_first_name") or not attrs.get("name_change_reason"):
                raise serializers.ValidationError("이름 변경은 변경할 이름과 사유를 입력해야 합니다.")
        required_kind = {
            SupportTicket.TicketType.CASH_PAYMENT: SupportTicket.RelatedKind.PURCHASE,
            SupportTicket.TicketType.TUTORING_FEE: SupportTicket.RelatedKind.TUTORING_REGISTRATION,
            SupportTicket.TicketType.PAYBACK: SupportTicket.RelatedKind.TUTORING_REGISTRATION,
        }.get(ticket_type)
        if required_kind and attrs.get("related_kind") != required_kind:
            raise serializers.ValidationError("이 문의 유형에는 연결 업무를 지정해야 합니다.")
        if attrs.get("related_kind"):
            validate_related_target(user=self.context["request"].user, related_kind=attrs["related_kind"], related_id=attrs.get("related_id"))
        return attrs

    def create(self, validated_data):
        from .services import add_event, display_name

        user = self.context["request"].user
        content = validated_data.pop("content")
        requested_role = validated_data.pop("requester_role", "")
        title = validated_data.pop("title", "") or TYPE_TITLES[validated_data["ticket_type"]]
        ticket = SupportTicket.objects.create(
            **validated_data,
            title=title,
            requester=user,
            requester_name=display_name(user),
            requester_role=ticket_role(user, requested_role),
        )
        message = SupportMessage.objects.create(ticket=ticket, sender=user, sender_name=display_name(user), sender_kind=SupportMessage.SenderKind.USER, content=content)
        SupportTicket.objects.filter(pk=ticket.pk).update(last_user_message_at=message.created_at)
        add_event(ticket, actor=user, event_type="ticket.created", payload={"ticket_type": ticket.ticket_type})
        ticket.refresh_from_db()
        return ticket


class SupportMessageCreateSerializer(serializers.Serializer):
    """사용자 추가 답변 본문입니다."""

    content = serializers.CharField()

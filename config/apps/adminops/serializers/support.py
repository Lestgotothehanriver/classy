"""관리자 문의 티켓 목록·상세 직렬화기입니다."""

from rest_framework import serializers

from config.apps.support.models import SupportTicket
from config.apps.support.serializers import SupportEventSerializer, SupportMessageSerializer
from config.apps.support.services import related_summary


class AdminSupportTicketSerializer(serializers.ModelSerializer):
    """운영자가 내부 메모까지 포함해 조회하는 티켓 표현입니다."""

    requester = serializers.SerializerMethodField()
    assignee = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id", "ticket_type", "status", "title", "requester", "assignee",
            "related_kind", "related_id", "related", "requested_last_name",
            "requested_first_name", "name_change_reason", "messages", "events",
            "created_at", "updated_at", "last_admin_message_at", "last_user_message_at",
            "resolved_at", "closed_at",
        ]

    def get_requester(self, obj):
        return {
            "id": obj.requester_id,
            "name": obj.requester_name,
            "user_name": obj.requester.user_name if obj.requester else "",
            "role": obj.requester_role,
        }

    def get_assignee(self, obj):
        if obj.assigned_to is None:
            return None
        return {"id": obj.assigned_to_id, "name": obj.assigned_to.user_name, "email": obj.assigned_to.email}

    def get_related(self, obj):
        return related_summary(obj)

    def get_messages(self, obj):
        if not self.context.get("detail"):
            return []
        return SupportMessageSerializer(obj.messages.all(), many=True).data

    def get_events(self, obj):
        if not self.context.get("detail"):
            return []
        return SupportEventSerializer(obj.events.all(), many=True).data


class AdminTicketReplySerializer(serializers.Serializer):
    """공개 답변과 선택 상태 전이 입력입니다."""

    content = serializers.CharField()
    status = serializers.ChoiceField(choices=SupportTicket.Status.choices, required=False)


class AdminTicketNoteSerializer(serializers.Serializer):
    """내부 메모 입력입니다."""

    content = serializers.CharField()


class AdminTicketAssignSerializer(serializers.Serializer):
    """담당자 배정 입력입니다. null은 미배정으로 되돌립니다."""

    assignee_id = serializers.IntegerField(required=False, allow_null=True)


class AdminTicketStatusSerializer(serializers.Serializer):
    """상태 변경과 선택 사유 입력입니다."""

    status = serializers.ChoiceField(choices=SupportTicket.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True)


class AdminNameChangeSerializer(serializers.Serializer):
    """이름 변경 승인 감사 사유입니다."""

    reason = serializers.CharField(required=False, allow_blank=True)

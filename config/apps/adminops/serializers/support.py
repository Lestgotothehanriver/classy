"""관리자 문의 티켓 목록·상세 직렬화기입니다."""

from rest_framework import serializers

from config.apps.support.models import SupportEvent, SupportTicket
from config.apps.support.serializers import SupportMessageSerializer
from config.apps.support.services import related_summary, status_label


class AdminSupportEventSerializer(serializers.ModelSerializer):
    """운영 감사용으로 처리자와 원본 변경값을 포함하는 티켓 이력입니다."""

    class Meta:
        model = SupportEvent
        fields = ["id", "actor_name", "event_type", "payload", "created_at"]


class AdminSupportTicketSerializer(serializers.ModelSerializer):
    """운영자가 내부 메모까지 포함해 조회하는 티켓 표현입니다."""

    requester = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    last_operator_name = serializers.SerializerMethodField()
    last_operator_at = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id", "ticket_type", "status", "status_label", "title", "requester",
            "last_operator_name", "last_operator_at",
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

    def get_status_label(self, obj):
        return status_label(obj.status)

    def get_last_operator_name(self, obj):
        return getattr(obj, "last_operator_name", "") or ""

    def get_last_operator_at(self, obj):
        return getattr(obj, "last_operator_at", None)

    def get_related(self, obj):
        return related_summary(obj)

    def get_messages(self, obj):
        if not self.context.get("detail"):
            return []
        return SupportMessageSerializer(obj.messages.all(), many=True).data

    def get_events(self, obj):
        if not self.context.get("detail"):
            return []
        return AdminSupportEventSerializer(obj.events.all(), many=True).data


class AdminTicketReplySerializer(serializers.Serializer):
    """공개 답변과 선택 상태 전이 입력입니다."""

    content = serializers.CharField()
    status = serializers.ChoiceField(choices=SupportTicket.Status.choices, required=False)


class AdminTicketNoteSerializer(serializers.Serializer):
    """내부 메모 입력입니다."""

    content = serializers.CharField()


class AdminTicketStatusSerializer(serializers.Serializer):
    """상태 변경과 선택 사유 입력입니다."""

    status = serializers.ChoiceField(choices=SupportTicket.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True)


class AdminNameChangeSerializer(serializers.Serializer):
    """이름 변경 승인 감사 사유입니다."""

    reason = serializers.CharField(required=False, allow_blank=True)

"""슈퍼관리자 전용 고객지원 채팅 직렬화기입니다."""

from rest_framework import serializers

from config.apps.support.models import SupportConversation
from config.apps.support.serializers import SupportConversationMessageSerializer


class AdminSupportConversationSerializer(serializers.ModelSerializer):
    """회원 식별 정보와 역할별 대화 내용을 관리자 화면에 제공합니다."""

    member = serializers.SerializerMethodField()
    unread_member_messages = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    action_targets = serializers.SerializerMethodField()

    class Meta:
        model = SupportConversation
        fields = [
            "id", "member", "role", "last_message", "unread_member_messages",
            "messages", "last_member_message_at", "last_operator_message_at",
            "action_targets", "created_at", "updated_at",
        ]

    def get_member(self, obj):
        return {"id": obj.member_id, "name": obj.member.user_name, "email": obj.member.email}

    def get_unread_member_messages(self, obj):
        """마지막 운영자 답변 뒤 새로 온 회원 메시지 유무를 목록용으로 반환한다."""
        if obj.last_member_message_at is None:
            return 0
        return int(
            obj.last_operator_message_at is None
            or obj.last_member_message_at > obj.last_operator_message_at
        )

    def get_last_message(self, obj):
        message = obj.messages.last()
        return SupportConversationMessageSerializer(message).data if message else None

    def get_messages(self, obj):
        if not self.context.get("detail"):
            return []
        return SupportConversationMessageSerializer(obj.messages.all(), many=True).data

    def get_action_targets(self, obj):
        """선택한 역할에서 실제로 열 수 있는 버튼 대상만 날짜와 함께 반환한다."""
        if not self.context.get("detail"):
            return {"tutoring_chats": [], "support_tickets": []}

        from config.apps.chat_app.models import ChatRoom
        from config.apps.support.models import SupportTicket

        role_filter = (
            {"student__user": obj.member}
            if obj.role == SupportConversation.Role.STUDENT
            else {"instructor__user": obj.member}
        )
        rooms = ChatRoom.objects.filter(**role_filter).select_related("post").order_by("-created_at", "-pk")
        tickets = SupportTicket.objects.filter(
            requester=obj.member,
            requester_role=obj.role,
        ).order_by("-updated_at", "-pk")
        return {
            "tutoring_chats": [
                {
                    "id": room.pk,
                    "label": room.title or room.post.title or f"과외 채팅방 #{room.pk}",
                    "created_at": room.created_at,
                }
                for room in rooms
            ],
            "support_tickets": [
                {
                    "id": ticket.pk,
                    "label": ticket.title,
                    "created_at": ticket.created_at,
                    "updated_at": ticket.updated_at,
                }
                for ticket in tickets
            ],
        }

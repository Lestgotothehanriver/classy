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

    class Meta:
        model = SupportConversation
        fields = [
            "id", "member", "role", "last_message", "unread_member_messages",
            "messages", "last_member_message_at", "last_operator_message_at",
            "created_at", "updated_at",
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

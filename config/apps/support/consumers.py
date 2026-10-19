"""역할별 고객지원 대화 전용 WebSocket consumer입니다."""

import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token

from .models import SupportConversation, SupportConversationMessage
from .serializers import SupportConversationMessageSerializer
from .services import add_conversation_message


class SupportConversationConsumer(AsyncWebsocketConsumer):
    """회원 본인 또는 슈퍼관리자만 역할별 고객지원방을 실시간 구독한다."""

    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"support_conversation_{self.conversation_id}"
        self.user = await self._user_from_token(self._token_key())
        if getattr(self.user, "is_anonymous", True):
            await self.close()
            return
        if not await self._can_access():
            await self.close()
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, _code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """텍스트 전송과 읽음 처리만 허용한다. 버튼 메시지는 관리자 REST API만 사용한다."""
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send(json.dumps({"event": "error", "message": "잘못된 메시지 형식입니다."}))
            return
        if data.get("type") == "read":
            if not self.user.is_superuser:
                await self._mark_member_read()
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "support.event", "payload": {"event": "read", "conversation_id": str(self.conversation_id)}},
                )
            return
        if data.get("type") != "message":
            return
        message = await self._save_text_message(data.get("text", ""))
        if message is None:
            await self.send(json.dumps({"event": "error", "message": "메시지 내용을 입력해주세요."}))
            return
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "support.event",
                "payload": {"event": "message", "conversation_id": str(self.conversation_id), "message": message},
            },
        )
        await self.channel_layer.group_send(
            "support_admin_inbox",
            {
                "type": "support.event",
                "payload": {"event": "message", "conversation_id": str(self.conversation_id), "message": message},
            },
        )

    def _token_key(self):
        query = parse_qs(self.scope["query_string"].decode())
        token_key = query.get("token", [None])[0]
        if token_key:
            return token_key
        headers = {key.decode().lower(): value.decode() for key, value in self.scope.get("headers", [])}
        parts = headers.get("authorization", "").split()
        return parts[1] if len(parts) == 2 and parts[0].lower() in {"token", "bearer"} else None

    @database_sync_to_async
    def _user_from_token(self, token_key):
        if not token_key:
            return AnonymousUser()
        try:
            return Token.objects.get(key=token_key).user
        except Token.DoesNotExist:
            return AnonymousUser()

    @database_sync_to_async
    def _can_access(self):
        return self.user.is_superuser or SupportConversation.objects.filter(
            pk=self.conversation_id,
            member=self.user,
        ).exists()

    @database_sync_to_async
    def _mark_member_read(self):
        from django.utils import timezone

        SupportConversation.objects.filter(pk=self.conversation_id, member=self.user).update(
            last_member_read_at=timezone.now(),
        )

    @database_sync_to_async
    def _save_text_message(self, content):
        conversation = SupportConversation.objects.select_related("member").filter(pk=self.conversation_id).first()
        if conversation is None:
            return None
        sender_kind = (
            SupportConversationMessage.SenderKind.OPERATOR
            if self.user.is_superuser
            else SupportConversationMessage.SenderKind.MEMBER
        )
        if not self.user.is_superuser and conversation.member_id != self.user.id:
            return None
        try:
            message = add_conversation_message(
                conversation,
                sender=self.user,
                sender_kind=sender_kind,
                content=content,
            )
        except Exception:
            return None
        return SupportConversationMessageSerializer(message).data

    async def support_event(self, event):
        """동기 API와 다른 소켓에서 발생한 이벤트를 현재 구독자에게 전달한다."""
        await self.send(json.dumps(event["payload"], default=str))

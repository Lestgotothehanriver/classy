"""
Notification WebSocket consumer.

Path: /ws/notifications/?token=<auth_token>

Server events:
  { "event": "unread_count", "student": 2, "instructor": 0 }
  { "event": "new_notification", "id": 1, "type": "...", "role": "...", "title": "...", "body": "...", "data": {}, "created_at": "..." }
"""

import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Authenticated user notification WebSocket.
    One user maps to one channel-layer group.
    """

    async def connect(self):
        token_key = self._extract_token()
        self.user = await self.get_user_from_token(token_key)
        logger.debug(
            "[BACKEND_DEBUG_NOTIFICATION] connect - user: %s, token: %s",
            self.user,
            bool(token_key),
        )

        if getattr(self.user, "is_anonymous", True):
            logger.warning("[BACKEND_DEBUG_NOTIFICATION] Rejected: anonymous user")
            await self.close()
            return

        self.group_name = f"notification_user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            "[BACKEND_DEBUG_NOTIFICATION] Connected: %s (group=%s)",
            self.user.email,
            self.group_name,
        )

        counts = await self.get_unread_counts()
        await self.send(json.dumps({"event": "unread_count", **counts}))

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )
            logger.info(
                "[BACKEND_DEBUG_NOTIFICATION] Disconnected: group=%s",
                self.group_name,
            )

    async def receive(self, text_data=None, bytes_data=None):
        logger.debug("[BACKEND_DEBUG_NOTIFICATION] receive: %s", text_data)
        try:
            data = json.loads(text_data or "{}")
            msg_type = data.get("type")

            if msg_type == "mark_read":
                notification_id = data.get("notification_id")
                if notification_id:
                    await self.mark_notification_read(int(notification_id))
                    counts = await self.get_unread_counts()
                    await self.send(json.dumps({"event": "unread_count", **counts}))

            elif msg_type == "mark_all_read":
                await self.mark_all_read()
                await self.send(
                    json.dumps(
                        {
                            "event": "unread_count",
                            "student": 0,
                            "instructor": 0,
                        }
                    )
                )

        except Exception as e:
            logger.error("*** [NotificationWS] receive error: %s ***", e)

    async def notification_new(self, event):
        logger.debug("[BACKEND_DEBUG_NOTIFICATION] notification_new: %s", event)
        await self.send(
            json.dumps(
                {
                    "event": "new_notification",
                    "id": event["id"],
                    "type": event["ntype"],
                    "role": event["role"],
                    "title": event["title"],
                    "body": event["body"],
                    "data": event.get("data", {}),
                    "created_at": event["created_at"],
                }
            )
        )
        counts = await self.get_unread_counts()
        await self.send(json.dumps({"event": "unread_count", **counts}))

    async def notification_counts(self, event):
        await self.send(
            json.dumps(
                {
                    "event": "unread_count",
                    "student": event.get("student", 0),
                    "instructor": event.get("instructor", 0),
                }
            )
        )

    @database_sync_to_async
    def get_unread_counts(self) -> dict:
        from config.apps.notification.models import Notification

        base = Notification.objects.filter(user=self.user, is_read=False)
        return {
            "student": base.filter(role="student").count(),
            "instructor": base.filter(role="instructor").count(),
        }

    @database_sync_to_async
    def mark_notification_read(self, pk: int):
        from config.apps.notification.models import Notification

        Notification.objects.filter(pk=pk, user=self.user).update(is_read=True)

    @database_sync_to_async
    def mark_all_read(self):
        from config.apps.notification.models import Notification

        Notification.objects.filter(user=self.user, is_read=False).update(
            is_read=True
        )

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        from rest_framework.authtoken.models import Token

        if not token_key:
            return AnonymousUser()
        try:
            return Token.objects.get(key=token_key).user
        except Token.DoesNotExist:
            return AnonymousUser()

    def _extract_token(self) -> str | None:
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        token = qs.get("token", [None])[0]
        if token:
            return token

        headers = dict(self.scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if auth.lower().startswith("token "):
            return auth.split(" ", 1)[1]
        return None

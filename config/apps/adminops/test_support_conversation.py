"""관리자 고객지원 대화 읽음 처리 API를 검증합니다."""

from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from config.apps.accounts.models import User
from config.apps.support.models import SupportConversation, SupportConversationMessage
from config.apps.support.realtime import consume_admin_realtime_ticket


class AdminSupportConversationReadTests(APITestCase):
    """관리자 열람 시각과 회원 메시지 읽음 표시를 검증합니다."""

    def setUp(self):
        """관리자·회원·고객지원 대화를 준비합니다."""
        self.admin = User.objects.create_user(
            username="support-admin",
            user_name="support-admin",
            password="pass1234",
            is_staff=True,
            is_superuser=True,
        )
        self.member = User.objects.create_user(
            username="support-member",
            user_name="support-member",
            password="pass1234",
        )
        self.conversation = SupportConversation.objects.create(
            member=self.member,
            role=SupportConversation.Role.STUDENT,
        )
        self.member_message = SupportConversationMessage.objects.create(
            conversation=self.conversation,
            sender=self.member,
            sender_kind=SupportConversationMessage.SenderKind.MEMBER,
            content="확인이 필요합니다.",
        )

    def test_non_superuser_cannot_mark_conversation_read(self):
        """일반 회원은 관리자 읽음 처리 API를 호출할 수 없습니다."""
        self.client.force_authenticate(self.member)

        response = self.client.post(
            f"/admin-api/v1/support-conversations/{self.conversation.pk}/read/",
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_read_marks_existing_member_messages_and_broadcasts(self):
        """관리자 열람은 기존 회원 메시지를 읽음으로 만들고 이벤트를 알립니다."""
        self.client.force_authenticate(self.member)
        before = self.client.get(f"/support/conversations/{self.conversation.pk}/")
        self.assertFalse(before.data["messages"][0]["is_read"])

        self.client.force_authenticate(self.admin)
        with patch(
            "config.apps.adminops.views.support.broadcast_conversation_event",
        ) as broadcast:
            response = self.client.post(
                f"/admin-api/v1/support-conversations/{self.conversation.pk}/read/",
            )

        self.assertEqual(response.status_code, 200)
        self.conversation.refresh_from_db()
        self.assertIsNotNone(self.conversation.last_operator_read_at)
        broadcast.assert_called_once_with(
            self.conversation,
            "operator_read",
            last_operator_read_at=self.conversation.last_operator_read_at,
        )

        self.client.force_authenticate(self.member)
        after = self.client.get(f"/support/conversations/{self.conversation.pk}/")
        self.assertTrue(after.data["messages"][0]["is_read"])

        later_message = SupportConversationMessage.objects.create(
            conversation=self.conversation,
            sender=self.member,
            sender_kind=SupportConversationMessage.SenderKind.MEMBER,
            content="새 메시지입니다.",
            created_at=timezone.now(),
        )
        latest = self.client.get(f"/support/conversations/{self.conversation.pk}/")
        rows = {row["id"]: row for row in latest.data["messages"]}
        self.assertFalse(rows[later_message.pk]["is_read"])

    def test_admin_realtime_ticket_is_single_use_and_never_contains_a_drf_token(self):
        """BFF가 받는 관리자 WebSocket 티켓은 한 번만 인증에 사용할 수 있다."""
        self.client.force_authenticate(self.admin)

        response = self.client.post("/admin-api/v1/realtime-ticket/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("ticket", response.data)
        self.assertIn("expires_at", response.data)
        self.assertIn("websocket_base_url", response.data)
        self.assertNotIn("token", response.data)
        self.assertEqual(consume_admin_realtime_ticket(response.data["ticket"]), self.admin)
        self.assertIsNone(consume_admin_realtime_ticket(response.data["ticket"]))

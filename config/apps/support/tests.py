"""1:1 문의 티켓 공개 API의 핵심 권한·표시 상태 테스트입니다."""

from datetime import date
from unittest.mock import patch

from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor, Student, Subject, User
from config.apps.accounts.serializers import (
    InstructorSignupSerializer,
    StudentSignupSerializer,
)
from config.apps.cash.models import PurchaseHistory
from config.apps.chat_app.models import ChatRoom
from config.apps.notification.models import Notification
from config.apps.tutoring.models import PaybackPayout, TutoringPost, TutoringRegistration

from .models import SupportConversation, SupportConversationMessage, SupportMessage, SupportTicket
from .services import (
    INSTRUCTOR_WELCOME_MESSAGE,
    KAKAO_CUSTOMER_CENTER_URL,
    STUDENT_PAYBACK_MESSAGE,
    STUDENT_WELCOME_MESSAGE,
    add_conversation_message,
    add_support_member_presence,
    ensure_support_conversation_with_onboarding,
    publish_support_conversation_message,
    remove_support_member_presence,
)


class SupportTicketApiTests(APITestCase):
    """사용자 티켓의 읽음 상태와 연결 대상 노출을 검증합니다."""

    def setUp(self):
        """테스트 사용자와 본인/타인 구매 내역을 준비합니다."""
        self.user = User.objects.create_user(
            username="support-user",
            user_name="support-user",
            password="pass1234",
        )
        self.other_user = User.objects.create_user(
            username="other-user",
            user_name="other-user",
            password="pass1234",
        )
        self.client.force_authenticate(self.user)

    def test_list_uses_korean_status_label_and_marks_admin_reply_read(self):
        """목록은 상태 표시명을 반환하고 상세 확인 후 새 답변 표시를 지웁니다."""
        ticket = SupportTicket.objects.create(
            requester=self.user,
            requester_name="문의 사용자",
            ticket_type=SupportTicket.TicketType.CASH_PAYMENT,
            status=SupportTicket.Status.RECEIVED,
            title="캐시 결제 문의",
        )
        message = SupportMessage.objects.create(
            ticket=ticket,
            sender_kind=SupportMessage.SenderKind.ADMIN,
            sender_name="운영자",
            content="확인 중입니다.",
        )
        ticket.last_admin_message_at = message.created_at
        ticket.save(update_fields=["last_admin_message_at"])

        before = self.client.get("/support/tickets/")

        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.data[0]["status_label"], "접수됨")
        self.assertEqual(before.data[0]["unread_admin_replies"], 1)

        read = self.client.post(f"/support/tickets/{ticket.pk}/read/")
        after = self.client.get("/support/tickets/")

        self.assertEqual(read.status_code, 200)
        self.assertEqual(after.data[0]["unread_admin_replies"], 0)

    def test_context_only_returns_requesters_purchase(self):
        """구매 연결 선택지는 로그인한 요청자의 내역으로만 제한합니다."""
        mine = PurchaseHistory.objects.create(
            user=self.user,
            platform="google",
            transaction_id="support-mine",
            purchased_cash=1000,
            paid_amount=1000,
            fee_deducted_amount=700,
            remaining_cash=1000,
        )
        PurchaseHistory.objects.create(
            user=self.other_user,
            platform="google",
            transaction_id="support-other",
            purchased_cash=2000,
            paid_amount=2000,
            fee_deducted_amount=1400,
            remaining_cash=2000,
        )

        response = self.client.get("/support/ticket-context/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["purchases"]], [mine.pk])

    def test_verification_ticket_requires_own_verification_target(self):
        """인증·프로필 유형은 검증된 인증 신청을 반드시 연결해야 합니다."""
        response = self.client.post(
            "/support/tickets/",
            {
                "ticket_type": SupportTicket.TicketType.VERIFICATION_PROFILE,
                "content": "인증 상태를 확인하고 싶어요.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_name_change_can_only_be_approved_once(self):
        """이름 변경 승인은 실제 이름과 상태를 한 번만 갱신합니다."""
        admin = User.objects.create_superuser(
            username="support-admin",
            user_name="support-admin",
            password="pass1234",
        )
        ticket = SupportTicket.objects.create(
            requester=self.user,
            requester_name="문의 사용자",
            ticket_type=SupportTicket.TicketType.NAME_CHANGE,
            status=SupportTicket.Status.RECEIVED,
            title="이름 변경 요청",
            requested_last_name="김",
            requested_first_name="클래씨",
            name_change_reason="개명",
        )
        self.client.force_authenticate(admin)

        first = self.client.post(f"/admin-api/v1/inquiries/{ticket.pk}/approve-name-change/")
        second = self.client.post(f"/admin-api/v1/inquiries/{ticket.pk}/approve-name-change/")

        self.user.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self.user.last_name, "김")
        self.assertEqual(self.user.first_name, "클래씨")
        self.assertEqual(ticket.status, SupportTicket.Status.RESOLVED)

    def test_payback_detail_is_only_available_to_the_student(self):
        """페이백 상세는 수령 대상 학생에게만 지급 상태를 노출합니다."""
        student = Student.objects.create(user=self.user)
        instructor_user = User.objects.create_user(
            username="payback-instructor",
            user_name="페이백강사",
            password="pass1234",
        )
        instructor = Instructor.objects.create(
            user=instructor_user,
            university="클래씨대학교",
            department="수학교육과",
            student_number="20260001",
        )
        subject = Subject.objects.create(number=9001)
        post = TutoringPost.objects.create(
            student=student,
            title="수학 과외",
            sex="여성",
            grade="고2",
            field="문과",
        )
        post.subjects.add(subject)
        room = ChatRoom.objects.create(student=student, instructor=instructor, post=post)
        registration = TutoringRegistration.objects.create(
            student=self.user,
            instructor=instructor_user,
            chat_room=room,
            subject=subject.name,
            start_date=date(2026, 10, 1),
            contract_status=TutoringRegistration.ContractStatus.ACTIVE,
        )
        PaybackPayout.objects.create(
            registration=registration,
            amount=15000,
            status=PaybackPayout.Status.COMPLETED,
        )

        mine = self.client.get(f"/support/payback-payouts/{registration.pk}/")
        self.client.force_authenticate(self.other_user)
        other = self.client.get(f"/support/payback-payouts/{registration.pk}/")

        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.data["payout"]["status_label"], "지급 완료")
        self.assertEqual(mine.data["payout"]["amount"], 15000)
        self.assertEqual(other.status_code, 404)


class SupportConversationOfficialProfileApiTests(APITestCase):
    """고객지원 대화가 공식 계정의 공개 프로필을 반환하는지 검증한다."""

    def setUp(self):
        self.member = User.objects.create_user(
            username="support-member",
            user_name="고객",
            password="pass1234",
        )
        self.official_user = User.objects.create_user(
            username="support-official",
            user_name="클래씨 고객지원",
            password="pass1234",
        )
        self.official_user.profile_image = "profile_images/support-official-profile.png"
        self.official_user.save(update_fields=["profile_image"])
        self.official = Instructor.objects.create(
            user=self.official_user,
            is_official_creator=True,
        )
        self.conversation = SupportConversation.objects.create(
            member=self.member,
            role=SupportConversation.Role.STUDENT,
        )
        self.client.force_authenticate(self.member)

    def test_list_and_detail_return_official_public_profile(self):
        """목록과 상세는 공식 계정의 이름·절대 이미지 URL을 같은 값으로 반환한다."""
        list_response = self.client.get("/support/conversations/?role=student")
        detail_response = self.client.get(
            f"/support/conversations/{self.conversation.pk}/"
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        for data in (list_response.data[0], detail_response.data):
            self.assertEqual(data["title"], self.official_user.user_name)
            self.assertEqual(data["official_instructor_id"], self.official.pk)
            self.assertTrue(data["profile_image"].endswith(self.official_user.profile_image.url))
            self.assertTrue(data["profile_image"].startswith("http://testserver/"))


class SupportConversationOnboardingTests(APITestCase):
    """가입 역할별 공식 고객지원방과 매크로 메시지를 검증합니다."""

    def setUp(self):
        """공개 발신자로 쓰일 단일 공식 계정을 준비합니다."""
        self.official_user = User.objects.create_user(
            username="official-onboarding",
            user_name="클래씨 안내",
            password="pass1234",
        )
        Instructor.objects.create(
            user=self.official_user,
            university="클래씨대학교",
            is_official_creator=True,
        )

    def test_student_signup_creates_two_distinct_onboarding_messages_once(self):
        """학생 가입은 안내와 페이백 메시지를 각각 한 번만 저장합니다."""
        serializer = StudentSignupSerializer(
            data={
                "email": "student-onboarding@example.com",
                "password": "pass12345",
                "user_name": "가입학생",
            },
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        conversation = SupportConversation.objects.get(
            member=user,
            role=SupportConversation.Role.STUDENT,
        )
        messages = list(conversation.messages.order_by("pk"))
        self.assertEqual(len(messages), 2)
        self.assertEqual(
            [message.onboarding_template_key for message in messages],
            ["student_welcome", "student_payback"],
        )
        self.assertEqual(messages[0].content, STUDENT_WELCOME_MESSAGE)
        self.assertEqual(messages[1].content, STUDENT_PAYBACK_MESSAGE)
        self.assertEqual(messages[0].sender, self.official_user)
        self.assertEqual(
            messages[0].action_type,
            SupportConversationMessage.ActionType.KAKAO_CUSTOMER_CENTER,
        )

        ensure_support_conversation_with_onboarding(user=user, role="student")
        self.assertEqual(conversation.messages.count(), 2)

        self.client.force_authenticate(user)
        response = self.client.get(f"/support/conversations/{conversation.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["messages"][0]["action"]["url"], KAKAO_CUSTOMER_CENTER_URL)
        self.assertEqual(response.data["messages"][0]["action"]["label"], "고객센터 바로가기")

    def test_instructor_signup_creates_one_onboarding_message_once(self):
        """선생님 가입은 선생님 전용 안내를 한 번만 저장합니다."""
        serializer = InstructorSignupSerializer(
            data={
                "email": "instructor-onboarding@example.com",
                "password": "pass12345",
                "user_name": "가입선생님",
                "university": "테스트대학교",
            },
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()

        conversation = SupportConversation.objects.get(
            member=user,
            role=SupportConversation.Role.INSTRUCTOR,
        )
        messages = list(conversation.messages.order_by("pk"))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].onboarding_template_key, "instructor_welcome")
        self.assertEqual(messages[0].content, INSTRUCTOR_WELCOME_MESSAGE)
        self.assertEqual(messages[0].sender, self.official_user)

        ensure_support_conversation_with_onboarding(user=user, role="instructor")
        self.assertEqual(conversation.messages.count(), 1)

    def test_operator_message_uses_chat_push_without_notification_record(self):
        """운영자 답변은 알림함을 만들지 않고 고객지원 채팅 이벤트로만 발행합니다."""
        member = User.objects.create_user(
            username="support-push-member",
            user_name="회원",
            password="pass1234",
        )
        Student.objects.create(user=member)
        conversation = SupportConversation.objects.create(
            member=member,
            role=SupportConversation.Role.STUDENT,
        )
        message = add_conversation_message(
            conversation,
            sender=self.official_user,
            sender_kind=SupportConversationMessage.SenderKind.OPERATOR,
            content="확인했습니다.",
        )

        with patch("config.apps.notification.fcm.send_push_to_user") as send_push:
            publish_support_conversation_message(conversation, message)

        send_push.assert_called_once()
        self.assertEqual(send_push.call_args.kwargs["data"]["type"], "message")
        self.assertEqual(
            send_push.call_args.kwargs["data"]["room_id"],
            f"support:{conversation.pk}",
        )
        self.assertEqual(
            send_push.call_args.kwargs["data"]["sender_name"],
            self.official_user.user_name,
        )
        self.assertFalse(Notification.objects.filter(user=member).exists())

    def test_open_support_room_skips_push_until_member_disconnects(self):
        """방을 연 회원은 WebSocket만 받고 FCM은 받지 않는다."""
        member = User.objects.create_user(
            username="support-online-member",
            user_name="온라인 회원",
            password="pass1234",
        )
        Student.objects.create(user=member)
        conversation = SupportConversation.objects.create(
            member=member,
            role=SupportConversation.Role.STUDENT,
        )
        message = add_conversation_message(
            conversation,
            sender=self.official_user,
            sender_kind=SupportConversationMessage.SenderKind.OPERATOR,
            content="실시간 확인",
        )
        add_support_member_presence(conversation.pk, member.pk, "test-channel")
        with patch("config.apps.notification.fcm.send_push_to_user") as send_push:
            publish_support_conversation_message(conversation, message)
        send_push.assert_not_called()

        remove_support_member_presence(conversation.pk, member.pk, "test-channel")
        with patch("config.apps.notification.fcm.send_push_to_user") as send_push:
            publish_support_conversation_message(conversation, message)
        send_push.assert_called_once()

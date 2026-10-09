"""1:1 문의 티켓 공개 API의 핵심 권한·표시 상태 테스트입니다."""

from datetime import date

from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor, Student, Subject, User
from config.apps.cash.models import PurchaseHistory
from config.apps.chat_app.models import ChatRoom
from config.apps.tutoring.models import PaybackPayout, TutoringPost, TutoringRegistration

from .models import SupportMessage, SupportTicket


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

"""관리자 운영 대시보드 API 테스트입니다."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from config.apps.accounts.models import Instructor, Student
from config.apps.cash.models import SettlementRecord
from config.apps.chat_app.models import ChatRoom
from config.apps.pending.models import PendingInstructor
from config.apps.report.models import Report, ReportStatusChoices
from config.apps.tutoring.models import (
    TutoringPost,
    TutoringRegistration,
    TutoringResource,
)

User = get_user_model()
PASSWORD = "Passw0rd!123"


def make_user(email, *, superuser=False, first="", last=""):
    """대시보드 테스트용 사용자를 생성합니다."""
    user = User.objects.create_user(
        username=email,
        email=email,
        user_name=email,
        password=PASSWORD,
        first_name=first,
        last_name=last,
    )
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])
    return user


class OperationsDashboardAPITests(APITestCase):
    """운영 대시보드의 권한·집계·우선순위 큐를 검증합니다."""

    URL = "/admin-api/v1/dashboard/operations/"

    def setUp(self):
        """각 운영 큐에 하나씩의 대기 항목을 만듭니다."""
        self.admin = make_user("root@example.com", superuser=True)
        self.admin_token = Token.objects.create(user=self.admin)
        self.now = timezone.now()

        self.reporter = make_user("reporter@example.com")
        self.reported = make_user("reported@example.com", first="신고", last="대상")
        self.report = Report.objects.create(
            reporter=self.reporter,
            reported_user=self.reported,
            status=ReportStatusChoices.PENDING,
        )
        Report.objects.filter(pk=self.report.pk).update(
            created_at=self.now - timedelta(days=4)
        )
        Report.objects.create(
            reporter=make_user("reviewer@example.com"),
            reported_user=self.reported,
            status=ReportStatusChoices.IN_REVIEW,
        )

        self.settlement_user = make_user("settlement@example.com", first="정산", last="강사")
        self.settlement_instructor = Instructor.objects.create(
            user=self.settlement_user,
            university="정산대학교",
        )
        self.settlement = SettlementRecord.objects.create(
            instructor=self.settlement_instructor,
            amount=125000,
            status="PENDING",
        )
        SettlementRecord.objects.filter(pk=self.settlement.pk).update(
            created_at=self.now - timedelta(days=3)
        )

        self.verification_user = make_user("verification@example.com", first="인증", last="강사")
        self.verification_instructor = Instructor.objects.create(
            user=self.verification_user,
            university="인증대학교",
        )
        self.verification = PendingInstructor.objects.create(
            instructor_profile=self.verification_instructor,
            status=PendingInstructor.Status.PENDING,
        )
        PendingInstructor.objects.filter(pk=self.verification.pk).update(
            applied_at=self.now - timedelta(days=1)
        )

        self.student_user = make_user("student@example.com", first="성사", last="학생")
        self.fee_user = make_user("fee@example.com", first="성사", last="강사")
        student = Student.objects.create(user=self.student_user)
        instructor = Instructor.objects.create(user=self.fee_user, university="성사대학교")
        post = TutoringPost.objects.create(student=student, title="수학 과외")
        room = ChatRoom.objects.create(
            student=student,
            instructor=instructor,
            post=post,
            initiated_by=self.student_user,
        )
        self.registration = TutoringRegistration.objects.create(
            student=self.student_user,
            instructor=self.fee_user,
            chat_room=room,
            subject="수학",
            start_date="2026-10-01",
        )
        TutoringRegistration.objects.filter(pk=self.registration.pk).update(
            updated_at=self.now - timedelta(days=2)
        )
        self.resource = TutoringResource.objects.create(
            student=student,
            instructor=instructor,
            registration=self.registration,
            fee_payment_status="AWAITING_CONFIRMATION",
        )

    def as_admin(self):
        """현재 API 클라이언트에 슈퍼관리자 인증을 설정합니다."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")

    def test_requires_superadmin(self):
        """익명과 일반 사용자는 운영 대시보드를 조회할 수 없습니다."""
        self.assertEqual(self.client.get(self.URL).status_code, 401)

        user = make_user("member@example.com")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_returns_summary_and_priority_queue(self):
        """상태별 집계와 안전·금전 우선 큐 순서를 반환합니다."""
        self.as_admin()

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        summary = response.data["summary"]
        self.assertEqual(summary["pending_reports"], 1)
        self.assertEqual(summary["reports_in_review"], 1)
        self.assertEqual(summary["awaiting_fee_confirmation"], 1)
        self.assertEqual(summary["pending_settlements"], 1)
        self.assertEqual(summary["pending_settlement_amount"], 125000)
        self.assertEqual(summary["pending_verifications"], 1)
        self.assertEqual(summary["action_required"], 4)

        queue = response.data["queue"]
        self.assertEqual(
            [item["kind"] for item in queue],
            ["report", "fee_confirmation", "settlement", "verification"],
        )
        self.assertEqual(queue[0]["target_id"], self.reported.pk)
        self.assertEqual(queue[1]["target_id"], self.registration.pk)
        self.assertEqual(queue[2]["target_id"], self.settlement.pk)
        self.assertEqual(queue[3]["target_id"], self.verification.pk)

    def test_returns_empty_queue_when_no_action_is_required(self):
        """처리 대기 항목이 없으면 빈 큐와 0건 요약을 반환합니다."""
        Report.objects.update(status=ReportStatusChoices.RESOLVED)
        TutoringResource.objects.update(fee_payment_status="PAID")
        SettlementRecord.objects.update(status="COMPLETED")
        PendingInstructor.objects.update(status=PendingInstructor.Status.VERIFIED)
        self.as_admin()

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["action_required"], 0)
        self.assertEqual(response.data["queue"], [])

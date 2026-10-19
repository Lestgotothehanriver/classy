"""무기한 누적 강사 랭킹 원장 집계의 회귀 테스트입니다."""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from config.apps.accounts.models import Instructor, Student, User, UserSanction
from config.apps.cash.instructor_lifetime_ranking import lifetime_rankings
from config.apps.cash.models import LectureRentalHistory
from config.apps.chat_app.models import ChatRoom
from config.apps.lecture.models import Lecture
from config.apps.tutoring.models import (
    CommissionInvoice,
    TutoringPost,
    TutoringRegistration,
)


class InstructorLifetimeRankingTest(TestCase):
    """유효한 강의 판매 캐시와 과외 수수료만 랭킹에 반영하는지 검증합니다."""

    def setUp(self):
        """랭킹 대상 강사와 강의 구매자를 생성합니다."""
        self.student_user = User.objects.create_user(
            username="lifetime_rank_student",
            user_name="랭킹 학생",
            password="password",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.first_instructor = self._create_instructor("first")
        self.second_instructor = self._create_instructor("second")
        self.third_instructor = self._create_instructor("third")

    def _create_instructor(self, suffix):
        """[suffix]를 식별자로 사용하는 활성 강사 계정을 생성합니다."""
        user = User.objects.create_user(
            username=f"lifetime_rank_{suffix}",
            user_name=f"랭킹 강사 {suffix}",
            password="password",
        )
        return Instructor.objects.create(user=user, university="클래씨대학교")

    def _create_rental(self, instructor, amount, *, is_canceled=False, is_sandbox=False):
        """[instructor]의 강의 판매 원장을 만들고 필요하면 제외 상태로 변경합니다."""
        lecture = Lecture.objects.create(
            title=f"강의 {instructor.pk}-{amount}",
            instructor=instructor,
            price=amount,
        )
        rental = LectureRentalHistory.objects.create(
            lecture=lecture,
            student=self.student_user,
            purchased_cash=amount,
            remaining_cash=0,
            is_canceled=is_canceled,
        )
        if is_sandbox:
            rental.is_sandbox = True
            rental.save(update_fields=["is_sandbox"])
        return rental

    def _create_registration(self, instructor, *, status):
        """[instructor]의 과외 계약과 연결 채팅방을 생성합니다."""
        post = TutoringPost.objects.create(
            student=self.student,
            title=f"랭킹 과외 {instructor.pk}",
        )
        room = ChatRoom.objects.create(
            student=self.student,
            instructor=instructor,
            post=post,
            initiated_by=self.student_user,
        )
        return TutoringRegistration.objects.create(
            student=self.student_user,
            instructor=instructor.user,
            chat_room=room,
            subject="수학",
            start_date=date.today(),
            contract_status=status,
        )

    def test_sums_paid_active_commissions_and_valid_lecture_sales(self):
        """최초·조정 납부 수수료와 강의 판매 캐시는 1:1로 합산됩니다."""
        registration = self._create_registration(
            self.first_instructor,
            status=TutoringRegistration.ContractStatus.ACTIVE,
        )
        CommissionInvoice.objects.create(
            registration=registration,
            invoice_type=CommissionInvoice.InvoiceType.INITIAL,
            base_amount=1_000,
            commission_rate_bps=1_000,
            commission_amount=100,
            status=CommissionInvoice.Status.PAID,
        )
        CommissionInvoice.objects.create(
            registration=registration,
            invoice_type=CommissionInvoice.InvoiceType.ADJUSTMENT,
            base_amount=500,
            commission_rate_bps=1_000,
            commission_amount=50,
            status=CommissionInvoice.Status.PAID,
        )
        self._create_rental(self.first_instructor, 300)

        rankings = lifetime_rankings()

        self.assertEqual(rankings[self.first_instructor.pk].score, 450)
        self.assertEqual(rankings[self.first_instructor.pk].rank, 1)

    def test_excludes_invalid_sales_invoices_and_inactive_contracts(self):
        """취소·샌드박스 판매와 미납 또는 비활성 계약 수수료는 제외됩니다."""
        self._create_rental(self.first_instructor, 100, is_canceled=True)
        self._create_rental(self.first_instructor, 100, is_sandbox=True)
        inactive_registration = self._create_registration(
            self.first_instructor,
            status=TutoringRegistration.ContractStatus.CANCELLED,
        )
        CommissionInvoice.objects.create(
            registration=inactive_registration,
            base_amount=1_000,
            commission_rate_bps=1_000,
            commission_amount=100,
            status=CommissionInvoice.Status.PAID,
        )
        pending_registration = self._create_registration(
            self.second_instructor,
            status=TutoringRegistration.ContractStatus.ACTIVE,
        )
        CommissionInvoice.objects.create(
            registration=pending_registration,
            base_amount=1_000,
            commission_rate_bps=1_000,
            commission_amount=100,
            status=CommissionInvoice.Status.PAYMENT_PENDING,
        )

        self.assertNotIn(self.first_instructor.pk, lifetime_rankings())
        self.assertNotIn(self.second_instructor.pk, lifetime_rankings())

    def test_competition_rank_and_withdrawal_recalculation(self):
        """동점은 1위·1위·3위이며 탈퇴하면 남은 강사의 순위가 즉시 갱신됩니다."""
        self._create_rental(self.first_instructor, 100)
        self._create_rental(self.second_instructor, 100)
        self._create_rental(self.third_instructor, 50)

        rankings = lifetime_rankings()
        self.assertEqual(rankings[self.first_instructor.pk].rank, 1)
        self.assertEqual(rankings[self.second_instructor.pk].rank, 1)
        self.assertEqual(rankings[self.third_instructor.pk].rank, 3)

        self.first_instructor.user.is_active = False
        self.first_instructor.user.deleted_at = timezone.now()
        self.first_instructor.user.save(update_fields=["is_active", "deleted_at"])

        rankings = lifetime_rankings()
        self.assertNotIn(self.first_instructor.pk, rankings)
        self.assertEqual(rankings[self.second_instructor.pk].rank, 1)
        self.assertEqual(rankings[self.third_instructor.pk].rank, 2)

    def test_warning_keeps_rank_and_effective_sanctions_temporarily_exclude(self):
        """경고는 유지하고, 유효 정지는 제외 후 만료·해제 시 기존 점수로 복귀합니다."""
        self._create_rental(self.first_instructor, 100)
        now = timezone.now()
        warning = UserSanction.objects.create(
            target_user=self.first_instructor.user,
            target_user_email=self.first_instructor.user.email,
            type=UserSanction.Type.WARNING,
            starts_at=now - timedelta(minutes=1),
        )

        self.assertIn(self.first_instructor.pk, lifetime_rankings())

        suspension = UserSanction.objects.create(
            target_user=self.first_instructor.user,
            target_user_email=self.first_instructor.user.email,
            type=UserSanction.Type.SUSPENSION,
            starts_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(days=1),
        )
        self.assertNotIn(self.first_instructor.pk, lifetime_rankings())

        suspension.expires_at = now - timedelta(seconds=1)
        suspension.save(update_fields=["expires_at"])
        self.assertIn(self.first_instructor.pk, lifetime_rankings())

        permanent_ban = UserSanction.objects.create(
            target_user=self.first_instructor.user,
            target_user_email=self.first_instructor.user.email,
            type=UserSanction.Type.PERMANENT_BAN,
            starts_at=now - timedelta(minutes=1),
        )
        self.assertNotIn(self.first_instructor.pk, lifetime_rankings())

        permanent_ban.is_active = False
        permanent_ban.save(update_fields=["is_active"])
        self.assertIn(self.first_instructor.pk, lifetime_rankings())
        self.assertTrue(warning.is_active)

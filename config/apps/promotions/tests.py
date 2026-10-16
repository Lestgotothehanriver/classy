"""출시 기념 강사 프로모션의 자격·사용 한도 테스트입니다."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from config.apps.accounts.models import Instructor, Student, User

from .models import PromotionCampaign
from .services import (
    active_benefit_for,
    assign_signup_promotion,
    promotion_summary_for,
    reserve_tutoring_benefit,
)


class InstructorPromotionBenefitTests(TestCase):
    """강사 가입 혜택이 신규 가입 시에만 확정되는지 검증합니다."""

    def setUp(self):
        """유효한 캠페인과 강사 프로필을 준비합니다."""
        self.now = timezone.now()
        self.campaign = PromotionCampaign.objects.create(
            name="출시 기념 프로모션",
            signup_starts_at=self.now - timedelta(days=1),
            signup_ends_at=self.now + timedelta(days=1),
        )
        self.user = User.objects.create_user(
            username="promotion-instructor",
            user_name="promotion-instructor",
            password="password123",
        )
        self.instructor = Instructor.objects.create(
            user=self.user,
            university="클래시대학교",
        )

    def test_assigns_snapshot_for_new_instructor_during_campaign(self):
        """기간 내 신규 강사는 캠페인 조건을 스냅샷으로 확정한다."""
        benefit = assign_signup_promotion(self.instructor, now=self.now)

        self.assertIsNotNone(benefit)
        self.assertEqual(benefit.campaign_id, self.campaign.id)
        self.assertEqual(benefit.tutoring_registration_limit, 3)
        self.assertEqual(benefit.tutoring_commission_rate_bps, 50)
        self.assertEqual(benefit.lecture_settlement_fee_rate_bps, 0)
        self.assertEqual(
            promotion_summary_for(self.instructor, now=self.now),
            {
                "ends_at": benefit.benefit_ends_at,
                "remaining_tutoring_registration_count": 3,
                "tutoring_registration_limit": 3,
                "tutoring_commission_rate_bps": 50,
                "lecture_settlement_fee_rate_bps": 0,
            },
        )

    def test_existing_student_role_addition_does_not_create_benefit(self):
        """기존 학생의 강사 역할·프로필 추가는 가입 혜택을 생성하지 않는다."""
        student_user = User.objects.create_user(
            username="existing-student",
            user_name="existing-student",
            password="password123",
        )
        Student.objects.create(user=student_user)
        Instructor.objects.create(user=student_user, university="클래시대학교")

        self.assertFalse(self.campaign.benefits.filter(instructor__user=student_user).exists())

    def test_tutoring_reservation_does_not_increment_usage(self):
        """수수료율 예약은 입금 확인 전 프로모션 사용 건수를 늘리지 않는다."""
        benefit = assign_signup_promotion(self.instructor, now=self.now)
        reserved_benefit, usage_number = reserve_tutoring_benefit(
            self.instructor,
            now=self.now,
        )

        self.assertEqual(reserved_benefit, benefit)
        self.assertIsNone(usage_number)
        benefit.refresh_from_db()
        self.assertEqual(benefit.used_tutoring_registration_count, 0)

    def test_campaign_and_benefit_end_instants_are_exclusive(self):
        """종료 시각 정각의 가입·성사·정산은 혜택을 적용하지 않는다."""
        self.assertIsNone(assign_signup_promotion(self.instructor, now=self.campaign.signup_ends_at))

        benefit = assign_signup_promotion(self.instructor, now=self.now)
        self.assertIsNotNone(benefit)
        self.assertIsNone(active_benefit_for(self.instructor, now=benefit.benefit_ends_at))
        self.assertEqual(
            reserve_tutoring_benefit(self.instructor, now=benefit.benefit_ends_at),
            (None, None),
        )

import json
import logging
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.utils import timezone

from config.apps.accounts.models import User, Student, Instructor, Subject
from config.apps.cash.models import InstructorMonthlyRank, LectureRentalHistory, SettlementRecord
from config.apps.lecture.models import Lecture

logger = logging.getLogger(__name__)

class MypageAPIViewSetTests(APITestCase):

    def setUp(self):
        # Create users
        self.student_user = User.objects.create_user(
            username="student_login", password="password", region="서울 강남구", user_name="student_user"
        )
        self.student = Student.objects.create(user=self.student_user)

        self.instructor_user = User.objects.create_user(
            username="instructor_login", password="password", region="서울 송파구", user_name="instructor_user"
        )
        self.instructor = Instructor.objects.create(user=self.instructor_user, university="서울대")

        # Create subjects 
        subj = Subject.objects.create(number=1)
        self.instructor.subjects.add(subj)

        now = timezone.now()
        
        self.lecture = Lecture.objects.create(
            title="Test Mypage Lecture",
            instructor=self.instructor,
            price=1500,
            is_delete=False
        )

        LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.student_user,
            purchased_cash=1500,
            remaining_cash=0,
            is_canceled=False,
            is_settled=False
        )
        history = LectureRentalHistory.objects.first()
        history.created_at = now
        history.save()

    def test_student_rented_lectures(self):
        url = reverse('student-rented-lectures')
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_student_liked_lectures(self):
        self.lecture.likes.add(self.student)
        url = reverse('student-liked-lectures')
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_instructor_uploaded_lectures(self):
        url = reverse('instructor-uploaded-lectures')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_instructor_settlement_info(self):
        url = reverse('instructor-settlement-info')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['settleable_revenue'], 1500)

    def test_instructor_request_settlement(self):
        url = reverse('instructor-request-settlement')
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount'], 1500)
        self.assertTrue(SettlementRecord.objects.filter(instructor=self.instructor).exists())


class InstructorSettlementFlowTests(APITestCase):
    """정산 신청/연결/중복방지/제외 조건 및 admin 상태 전이 검증."""

    def setUp(self):
        self.student_user = User.objects.create_user(
            username="s_flow", password="pw", user_name="s_flow"
        )
        self.student = Student.objects.create(user=self.student_user)

        self.instructor_user = User.objects.create_user(
            username="i_flow", password="pw", user_name="i_flow"
        )
        self.instructor = Instructor.objects.create(user=self.instructor_user, university="서울대")

        self.lecture = Lecture.objects.create(
            title="Flow Lecture", instructor=self.instructor, price=2000, is_delete=False
        )

        self.request_url = reverse('instructor-request-settlement')
        self.info_url = reverse('instructor-settlement-info')
        self.client.force_authenticate(user=self.instructor_user)

    def _rental(self, cash=2000, is_canceled=False, is_settled=False):
        return LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.student_user,
            purchased_cash=cash,
            remaining_cash=0,
            is_canceled=is_canceled,
            is_settled=is_settled,
        )

    def test_request_links_rentals_to_record(self):
        """신청 성공 시 대상 대여가 is_settled=True, settlement=<record>로 연결된다."""
        r1 = self._rental()
        r2 = self._rental()

        resp = self.client.post(self.request_url)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['amount'], 4000)

        record = SettlementRecord.objects.get(instructor=self.instructor)
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertTrue(r1.is_settled)
        self.assertTrue(r2.is_settled)
        self.assertEqual(r1.settlement_id, record.id)
        self.assertEqual(r2.settlement_id, record.id)

    def test_excludes_canceled_zero_cash_and_settled(self):
        """취소/0캐시/이미정산 대여는 정산 대상에서 제외된다."""
        payable = self._rental(cash=2000)
        self._rental(cash=2000, is_canceled=True)   # 취소 → 제외
        self._rental(cash=0)                         # 무료/0캐시 → 제외
        self._rental(cash=2000, is_settled=True)     # 이미 정산 → 제외

        resp = self.client.post(self.request_url)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['amount'], 2000)

        record = SettlementRecord.objects.get(instructor=self.instructor)
        # 오직 payable 대여만 이번 record에 귀속된다.
        self.assertEqual(list(record.rentals.values_list('id', flat=True)), [payable.id])

    def test_repeated_request_does_not_double_settle(self):
        """연속 신청 시 같은 대여가 중복 정산되지 않고, 두 번째는 400을 반환한다."""
        self._rental(cash=2000)

        first = self.client.post(self.request_url)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(self.request_url)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', second.data)
        # 정산 건은 하나만 생성된다.
        self.assertEqual(SettlementRecord.objects.filter(instructor=self.instructor).count(), 1)

    def test_no_settleable_returns_400(self):
        resp = self.client.post(self.request_url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SettlementRecord.objects.filter(instructor=self.instructor).exists())

    def _admin_save(self, record, new_status):
        """Django admin save_model을 통해 상태 전이 처리를 실행한다."""
        from django.contrib.admin.sites import AdminSite
        from config.apps.cash.admin import SettlementRecordAdmin
        record.status = new_status
        SettlementRecordAdmin(SettlementRecord, AdminSite()).save_model(
            request=None, obj=record, form=None, change=True
        )

    def test_admin_complete_updates_revenue_and_processed_at(self):
        """admin COMPLETED 처리 시 completed_revenue↑, pending_revenue↓, processed_at 기록."""
        self._rental(cash=2000)
        self.client.post(self.request_url)
        record = SettlementRecord.objects.get(instructor=self.instructor)

        info_before = self.client.get(self.info_url).data
        self.assertEqual(info_before['pending_revenue'], 2000)
        self.assertEqual(info_before['completed_revenue'], 0)

        self._admin_save(record, 'COMPLETED')
        record.refresh_from_db()
        self.assertIsNotNone(record.processed_at)

        info_after = self.client.get(self.info_url).data
        self.assertEqual(info_after['pending_revenue'], 0)
        self.assertEqual(info_after['completed_revenue'], 2000)

    def test_admin_cancel_reverts_rentals_and_allows_resubmit(self):
        """admin CANCELED 처리 시 연결 대여가 롤백되어 재신청 가능하고, 합계에서 제외된다."""
        rental = self._rental(cash=2000)
        self.client.post(self.request_url)
        record = SettlementRecord.objects.get(instructor=self.instructor)

        self._admin_save(record, 'CANCELED')
        record.refresh_from_db()
        rental.refresh_from_db()

        self.assertIsNotNone(record.processed_at)
        self.assertFalse(rental.is_settled)
        self.assertIsNone(rental.settlement_id)

        # CANCELED 건은 강사 화면 합계에서 제외되고, 대여는 다시 정산 가능.
        info = self.client.get(self.info_url).data
        self.assertEqual(info['pending_revenue'], 0)
        self.assertEqual(info['completed_revenue'], 0)
        self.assertEqual(info['settleable_revenue'], 2000)

        # 재신청 성공.
        resub = self.client.post(self.request_url)
        self.assertEqual(resub.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resub.data['amount'], 2000)

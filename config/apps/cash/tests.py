from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from config.apps.cash.models import PurchaseHistory
from unittest.mock import patch

User = get_user_model()


class CashPurchaseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('cash:purchase')

    # ── Apple 결제 성공 ─────────────────────────
    @patch('config.apps.cash.views.verify_apple_receipt')
    def test_apple_purchase_success(self, mock_verify):
        mock_verify.return_value = (True, 'apple_tx_001', '')

        resp = self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'valid_receipt_base64',
            'product_id': 'cash_1000',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['purchased_cash'], 1000)
        self.assertEqual(resp.data['remaining_cash'], 1000)

        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 1000)

        history = PurchaseHistory.objects.get(transaction_id='apple_tx_001')
        self.assertEqual(history.platform, 'apple')
        self.assertEqual(history.purchased_cash, 1000)
        self.assertEqual(history.paid_amount, 1000)
        self.assertEqual(history.fee_deducted_amount, 700)
        self.assertEqual(history.remaining_cash, 1000)

    # ── Google 결제 성공 ────────────────────────
    @patch('config.apps.cash.views.verify_google_receipt')
    def test_google_purchase_success(self, mock_verify):
        mock_verify.return_value = (True, 'GPA.1234-5678', '')

        resp = self.client.post(self.url, {
            'platform': 'google',
            'purchase_token': 'valid_token_abc',
            'product_id': 'cash_5000',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['purchased_cash'], 5000)

        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 5000)

    # ── 중복 트랜잭션 차단 (409 Conflict) ──────────
    @patch('config.apps.cash.views.verify_apple_receipt')
    def test_duplicate_transaction_rejected(self, mock_verify):
        mock_verify.return_value = (True, 'dup_tx_999', '')

        PurchaseHistory.objects.create(
            user=self.user,
            platform='apple',
            transaction_id='dup_tx_999',
            purchased_cash=5000,
            paid_amount=5000,
            fee_deducted_amount=3500,
            remaining_cash=5000,
        )

        resp = self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'some_receipt',
            'product_id': 'cash_5000',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('already been processed', resp.data['error'])

        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 0)

    # ── 검증 실패 시 캐시 미지급 ──────────────────
    @patch('config.apps.cash.views.verify_apple_receipt')
    def test_verification_failure_no_cash(self, mock_verify):
        mock_verify.return_value = (False, None, 'Invalid receipt (status=21003).')

        resp = self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'invalid_receipt',
            'product_id': 'cash_1000',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('verification failed', resp.data['error'])

        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 0)
        self.assertEqual(PurchaseHistory.objects.count(), 0)

    # ── 존재하지 않는 product_id ──────────────────
    @patch('config.apps.cash.views.verify_apple_receipt')
    def test_invalid_product_id(self, mock_verify):
        resp = self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'some_receipt',
            'product_id': 'cash_999999',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        mock_verify.assert_not_called()

    # ── 인증 없이 접근 시 401 ─────────────────────
    def test_unauthenticated_request(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'r',
            'product_id': 'cash_1000',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── 연속 구매 시 캐시 누적 확인 ─────────────────
    @patch('config.apps.cash.views.verify_apple_receipt')
    def test_cumulative_cash(self, mock_verify):
        mock_verify.side_effect = [
            (True, 'tx_a', ''),
            (True, 'tx_b', ''),
        ]

        self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'r1',
            'product_id': 'cash_1000',
        }, format='json')

        self.client.post(self.url, {
            'platform': 'apple',
            'receipt_data': 'r2',
            'product_id': 'cash_5000',
        }, format='json')

        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 6000)
        self.assertEqual(PurchaseHistory.objects.filter(user=self.user).count(), 2)

from config.apps.cash.models import LectureRentalHistory
from config.apps.lecture.models import Lecture
from config.apps.accounts.models import Instructor, Subject, Student
from django.core.files.uploadedfile import SimpleUploadedFile
from datetime import timedelta
from django.utils import timezone

class RentalAndRefundTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='student1', password='pw')
        self.user.cash = 10000
        self.user.save()
        self.student = Student.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)
        
        # Setup lecture
        self.instructor_user = User.objects.create_user(username='inst1', password='pw')
        self.instructor = Instructor.objects.create(user=self.instructor_user, university='Test Univ')
        self.lecture = Lecture.objects.create(
            instructor=self.instructor,
            title="Test Lecture",
            price=3000,
            rental_period=30
        )
        
        self.rent_url = reverse('cash:lecture-rent')

    def test_lecture_rental_success(self):
        resp = self.client.post(self.rent_url, {'lecture_id': self.lecture.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['remaining_cash'], 7000)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 7000)
        self.assertTrue(LectureRentalHistory.objects.filter(student=self.user, lecture=self.lecture).exists())

    def test_lecture_rental_insufficient_cash(self):
        self.user.cash = 1000
        self.user.save()
        resp = self.client.post(self.rent_url, {'lecture_id': self.lecture.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lecture_rental_duplicate(self):
        # Create active rental
        LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000
        )
        resp = self.client.post(self.rent_url, {'lecture_id': self.lecture.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('active rental', resp.data['error'])

    def test_lecture_rental_cancel_success(self):
        rental = LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000
        )
        self.user.cash = 7000
        self.user.save()
        
        cancel_url = reverse('cash:lecture-rent-cancel', args=[rental.id])
        resp = self.client.post(cancel_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 10000)
        rental.refresh_from_db()
        self.assertTrue(rental.is_canceled)

    def test_lecture_rental_cancel_after_7_days(self):
        rental = LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000
        )
        self.user.cash = 7000
        self.user.save()
        
        # Manually change created_at
        rental.created_at = timezone.now() - timedelta(days=8)
        rental.save()
        
        cancel_url = reverse('cash:lecture-rent-cancel', args=[rental.id])
        resp = self.client.post(cancel_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('7 days', resp.data['error'])



        refund_url = reverse('cash:apple-webhook')
        resp = self.client.post(refund_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lecture_detail_rental_status(self):
        detail_url = reverse('lecture-detail', args=[self.lecture.id])
        
        # 1. none
        resp = self.client.get(detail_url)
        self.assertEqual(resp.data['rental_status'], 'none')
        
        # 2. valid
        rental = LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000
        )
        resp = self.client.get(detail_url)
        self.assertEqual(resp.data['rental_status'], 'valid')
        
        # 3. expired
        rental.created_at = timezone.now() - timedelta(days=31)
        rental.save()
        resp = self.client.get(detail_url)
        self.assertEqual(resp.data['rental_status'], 'expired')
        
        # 4. none again when all are canceled (the current implementation assumes valid is skipped and expired is skipped if no non-canceled exist)
        rental.is_canceled = True
        rental.save()
        resp = self.client.get(detail_url)
        self.assertEqual(resp.data['rental_status'], 'none')

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

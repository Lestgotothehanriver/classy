from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from config.apps.accounts.models import Instructor, Student
from config.apps.cash.apple_iap import (
    AppleIAPVerificationError,
    VerifiedAppleTransaction,
)
from config.apps.cash.models import LectureRentalHistory, PurchaseHistory
from config.apps.lecture.models import Lecture

User = get_user_model()


def verified_transaction(
    user,
    *,
    transaction_id='apple_tx_001',
    product_id='cash_1000',
    price_milliunits=1_200_000,
):
    return VerifiedAppleTransaction(
        transaction_id=transaction_id,
        original_transaction_id=transaction_id,
        product_id=product_id,
        app_account_token=user.apple_app_account_token,
        environment='Sandbox',
        purchase_date=timezone.now(),
        price_milliunits=price_milliunits,
        currency='KRW',
        storefront='KOR',
        revocation_date=None,
        revocation_percentage=0,
    )


class CashPurchaseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser', password='testpassword', user_name='testuser'
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('cash:purchase')
        self.throttle_patcher = patch(
            'rest_framework.throttling.SimpleRateThrottle.allow_request',
            return_value=True,
        )
        self.throttle_patcher.start()

    def tearDown(self):
        self.throttle_patcher.stop()

    def _purchase(self, product_id='cash_1000', signed_payload='signed-jws'):
        return self.client.post(
            self.url,
            {
                'platform': 'apple',
                'signed_transaction_info': signed_payload,
                'product_id': product_id,
            },
            format='json',
        )

    @patch('config.apps.cash.views.verify_apple_transaction')
    def test_apple_purchase_success_uses_signed_price(self, mock_verify):
        mock_verify.return_value = verified_transaction(self.user)

        response = self._purchase()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['purchased_cash'], 1000)
        self.assertEqual(response.data['credited_cash'], 1000)
        self.assertEqual(response.data['remaining_cash'], 1000)
        self.assertFalse(response.data['idempotent'])
        mock_verify.assert_called_once_with(
            'signed-jws',
            expected_product_id='cash_1000',
            expected_app_account_token=self.user.apple_app_account_token,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 1000)
        history = PurchaseHistory.objects.get(transaction_id='apple_tx_001')
        self.assertEqual(history.product_id, 'cash_1000')
        self.assertEqual(history.paid_amount, 1200)
        self.assertEqual(history.fee_deducted_amount, 840)

    @patch('config.apps.cash.views.verify_apple_transaction')
    def test_same_transaction_is_idempotent(self, mock_verify):
        mock_verify.return_value = verified_transaction(
            self.user, transaction_id='apple_tx_idempotent'
        )

        first = self._purchase()
        second = self._purchase()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['idempotent'])
        self.assertEqual(second.data['credited_cash'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 1000)
        self.assertEqual(PurchaseHistory.objects.count(), 1)

    @patch('config.apps.cash.views.verify_apple_transaction')
    def test_verification_failure_does_not_credit_cash(self, mock_verify):
        mock_verify.side_effect = AppleIAPVerificationError(
            'Apple transaction verification failed.'
        )

        response = self._purchase(signed_payload='invalid-jws')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 0)
        self.assertEqual(PurchaseHistory.objects.count(), 0)

    @patch('config.apps.cash.views.verify_apple_transaction')
    def test_invalid_product_id_is_rejected_before_apple_check(self, mock_verify):
        response = self._purchase(product_id='cash_999999')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_verify.assert_not_called()

    def test_google_platform_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                'platform': 'google',
                'signed_transaction_info': 'signed-jws',
                'product_id': 'cash_1000',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self._purchase().status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('config.apps.cash.views.verify_apple_transaction')
    def test_future_purchase_offsets_refund_debt_first(self, mock_verify):
        self.user.cash_debt = 600
        self.user.save(update_fields=['cash_debt'])
        mock_verify.return_value = verified_transaction(self.user)

        response = self._purchase()

        self.assertEqual(response.data['debt_offset'], 600)
        self.assertEqual(response.data['credited_cash'], 400)
        self.user.refresh_from_db()
        self.assertEqual((self.user.cash, self.user.cash_debt), (400, 0))

    def test_package_list_returns_stable_apple_account_token(self):
        response = self.client.get(reverse('cash:packages'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 6)
        self.assertTrue(
            all(item['platform'] == 'apple' for item in response.data['results'])
        )
        self.assertTrue(
            all(
                item['appAccountToken'] == str(self.user.apple_app_account_token)
                for item in response.data['results']
            )
        )


class CashToLectureIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='student1', password='password', user_name='student1'
        )
        Student.objects.create(user=self.user)
        instructor_user = User.objects.create_user(
            username='instructor1', password='password', user_name='instructor1'
        )
        instructor = Instructor.objects.create(
            user=instructor_user, university='Test University'
        )
        self.lecture = Lecture.objects.create(
            instructor=instructor,
            title='Apple purchase integration lecture',
            price=3000,
            rental_period=30,
        )
        self.client.force_authenticate(self.user)

    @patch('config.apps.cash.views.verify_apple_transaction')
    def test_verified_cash_purchase_can_immediately_rent_lecture(self, mock_verify):
        mock_verify.return_value = verified_transaction(
            self.user,
            transaction_id='cash_to_lecture_tx',
            product_id='cash_5000',
            price_milliunits=6_000_000,
        )
        purchase = self.client.post(
            reverse('cash:purchase'),
            {
                'platform': 'apple',
                'signed_transaction_info': 'signed-jws',
                'product_id': 'cash_5000',
            },
            format='json',
        )
        self.assertEqual(purchase.status_code, status.HTTP_200_OK)
        self.assertEqual(purchase.data['remaining_cash'], 5000)

        rental = self.client.post(
            reverse('cash:lecture-rent'),
            {'lecture_id': self.lecture.id},
            format='json',
        )

        self.assertEqual(rental.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rental.data['remaining_cash'], 2000)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 2000)
        self.assertTrue(
            LectureRentalHistory.objects.filter(
                student=self.user, lecture=self.lecture, is_canceled=False
            ).exists()
        )


class RentalPolicyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='rental-student', password='password', user_name='rental-student'
        )
        self.user.cash = 10_000
        self.user.save(update_fields=['cash'])
        Student.objects.create(user=self.user)
        instructor_user = User.objects.create_user(
            username='rental-instructor',
            password='password',
            user_name='rental-instructor',
        )
        instructor = Instructor.objects.create(
            user=instructor_user, university='Test University'
        )
        self.lecture = Lecture.objects.create(
            instructor=instructor,
            title='Rental policy lecture',
            price=3000,
            rental_period=30,
        )
        self.client.force_authenticate(self.user)

    def test_lecture_rental_success(self):
        response = self.client.post(
            reverse('cash:lecture-rent'),
            {'lecture_id': self.lecture.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['remaining_cash'], 7000)

    def test_lecture_rental_insufficient_cash(self):
        self.user.cash = 1000
        self.user.save(update_fields=['cash'])
        response = self.client.post(
            reverse('cash:lecture-rent'),
            {'lecture_id': self.lecture.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lecture_rental_duplicate(self):
        LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000,
        )
        response = self.client.post(
            reverse('cash:lecture-rent'),
            {'lecture_id': self.lecture.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('active rental', response.data['error'])

    def test_lecture_rental_cannot_be_canceled(self):
        rental = LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000,
        )
        response = self.client.post(
            reverse('cash:lecture-rent-cancel', args=[rental.id]), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        rental.refresh_from_db()
        self.assertFalse(rental.is_canceled)

    def test_lecture_detail_reports_expired_rental(self):
        rental = LectureRentalHistory.objects.create(
            lecture=self.lecture,
            student=self.user,
            purchased_cash=self.lecture.price,
            remaining_cash=7000,
        )
        rental.expiration_date = timezone.now() - timezone.timedelta(seconds=1)
        rental.save(update_fields=['expiration_date'])
        response = self.client.get(reverse('lecture-detail', args=[self.lecture.id]))
        self.assertEqual(response.data['rental_status'], 'expired')

    def test_apple_webhook_requires_signed_payload(self):
        response = self.client.post(reverse('cash:apple-webhook'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

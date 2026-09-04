"""Focused tests for the Google Play Billing implementation."""

import base64
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .constants import GOOGLE_PRODUCT_CASH_MAP
from .google_iap import (
    GoogleIAPVerificationError,
    VerifiedGooglePurchase,
    apply_google_voided_purchase,
    process_google_notification,
    verify_pubsub_oidc_token,
)
from .models import (
    GooglePlayPurchase,
    GooglePlaySyncState,
    GooglePlayWebhookEvent,
    PurchaseHistory,
)
from .serializers import CashPurchaseSerializer

User = get_user_model()


def google_response(user, **overrides):
    """Return a valid Publisher API response with optional overrides."""

    response = {
        'purchaseState': 0,
        'quantity': 1,
        'consumptionState': 0,
        'acknowledgementState': 1,
        'obfuscatedExternalAccountId': str(user.google_play_account_token),
        'purchaseTimeMillis': '1788480000000',
        'orderId': 'GPA.1234-5678-9012-34567',
    }
    response.update(overrides)
    return response


def verified_purchase(user, *, token='google-token', order_id='GPA.voided'):
    """Build a trusted purchase object for ledger-only tests."""

    return VerifiedGooglePurchase(
        purchase_token=token,
        product_id='cash_1000',
        order_id=order_id,
        account_token=user.google_play_account_token,
        purchase_time=timezone.now(),
        purchase_state='PURCHASED',
        acknowledgement_state='ACKNOWLEDGED',
        consumption_state='NOT_CONSUMED',
    )


@override_settings(
    GOOGLE_PLAY_PACKAGE_NAME='com.classystudy.app',
    GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64='configured-in-test',
)
class GooglePurchaseApiTests(TestCase):
    """Exercise validation, idempotency, and server consumption through the API."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='google-user',
            password='password',
            user_name='google-user',
        )
        self.client.force_authenticate(self.user)
        self.products = MagicMock()
        self.service = MagicMock()
        self.service.purchases.return_value.products.return_value = self.products
        self.products.get.return_value.execute.return_value = google_response(
            self.user
        )
        self.products.consume.return_value.execute.return_value = {}
        self.publisher_patcher = patch(
            'config.apps.cash.google_iap._publisher_service',
            return_value=self.service,
        )
        self.publisher_patcher.start()
        self.throttle_patcher = patch(
            'rest_framework.throttling.SimpleRateThrottle.allow_request',
            return_value=True,
        )
        self.throttle_patcher.start()

    def tearDown(self):
        self.publisher_patcher.stop()
        self.throttle_patcher.stop()

    def _purchase(self, *, token='google-token', product_id='cash_1000'):
        return self.client.post(
            reverse('cash:purchase'),
            {
                'platform': 'google',
                'product_id': product_id,
                'purchase_token': token,
            },
            format='json',
        )

    def test_serializer_requires_store_specific_proof(self):
        serializer = CashPurchaseSerializer(data={
            'platform': 'google',
            'product_id': 'cash_1000',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('purchase_token', serializer.errors)

    def test_google_package_list_has_five_products_and_account_id(self):
        response = self.client.get(reverse('cash:packages'), {'platform': 'google'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item['productId'] for item in response.data['results']},
            set(GOOGLE_PRODUCT_CASH_MAP),
        )
        self.assertEqual(len(response.data['results']), 5)
        self.assertTrue(all(item['platform'] == 'google' for item in response.data['results']))
        self.assertTrue(all(
            item['obfuscatedAccountId'] == str(self.user.google_play_account_token)
            for item in response.data['results']
        ))

    def test_purchase_grants_once_and_consumes_on_server(self):
        response = self._purchase()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['purchased_cash'], 1000)
        self.assertEqual(response.data['credited_cash'], 1000)
        self.assertFalse(response.data['idempotent'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 1000)
        detail = GooglePlayPurchase.objects.select_related('purchase_history').get()
        self.assertEqual(detail.consumption_state, 'CONSUMED')
        self.assertEqual(detail.purchase_history.platform, 'google')
        self.products.get.assert_called_once_with(
            packageName='com.classystudy.app',
            productId='cash_1000',
            token='google-token',
        )
        self.products.consume.assert_called_once_with(
            packageName='com.classystudy.app',
            productId='cash_1000',
            token='google-token',
        )

    def test_pending_purchase_is_rejected_without_credit(self):
        self.products.get.return_value.execute.return_value = google_response(
            self.user,
            purchaseState=2,
        )

        response = self._purchase()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 0)
        self.assertFalse(PurchaseHistory.objects.exists())

    def test_canceled_or_multi_quantity_purchase_is_rejected(self):
        for response_overrides in (
            {'purchaseState': 1},
            {'quantity': 2},
        ):
            with self.subTest(response_overrides=response_overrides):
                self.products.get.return_value.execute.return_value = google_response(
                    self.user,
                    **response_overrides,
                )
                response = self._purchase(token=f"token-{response_overrides}")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PurchaseHistory.objects.exists())

    def test_unknown_product_is_rejected_before_google_api_call(self):
        response = self._purchase(product_id='cash_999999')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.products.get.assert_not_called()

    def test_account_mismatch_is_conflict(self):
        other = User.objects.create_user(
            username='google-other', password='password', user_name='google-other'
        )
        self.products.get.return_value.execute.return_value = google_response(
            other
        )

        response = self._purchase()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(PurchaseHistory.objects.exists())

    def test_same_token_is_idempotent_but_other_user_conflicts(self):
        first = self._purchase()
        second = self._purchase()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['idempotent'])
        self.assertEqual(second.data['credited_cash'], 0)
        other = User.objects.create_user(
            username='token-thief', password='password', user_name='token-thief'
        )
        self.client.force_authenticate(other)
        conflict = self._purchase()
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)

    def test_consume_failure_keeps_grant_and_retry_only_consumes(self):
        self.products.consume.return_value.execute.side_effect = RuntimeError('offline')

        first = self._purchase()

        self.assertEqual(first.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 1000)
        self.assertEqual(
            GooglePlayPurchase.objects.get().consumption_state,
            'NOT_CONSUMED',
        )

        self.products.consume.return_value.execute.side_effect = None
        self.products.consume.return_value.execute.return_value = {}
        second = self._purchase()

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['idempotent'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.cash, 1000)
        self.assertEqual(GooglePlayPurchase.objects.get().consumption_state, 'CONSUMED')


@override_settings(
    GOOGLE_PLAY_PACKAGE_NAME='com.classystudy.app',
    GOOGLE_PLAY_RTDN_AUDIENCE='https://api.example.com/cash/webhook/google/',
    GOOGLE_PLAY_RTDN_SERVICE_ACCOUNT_EMAIL='pubsub@example.iam.gserviceaccount.com',
)
class GoogleRtdnAndRefundTests(TestCase):
    """Exercise RTDN authentication boundaries and voided purchase recovery."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='rtdn-user', password='password', user_name='rtdn-user'
        )

    def _envelope(self, *, message_id='message-1'):
        payload = {
            'packageName': 'com.classystudy.app',
            'oneTimeProductNotification': {
                'notificationType': 1,
                'productId': 'cash_1000',
                'purchaseToken': 'rtdn-token',
            },
        }
        return {
            'message': {
                'messageId': message_id,
                'data': base64.b64encode(
                    json.dumps(payload).encode('utf-8')
                ).decode('ascii'),
            }
        }

    @patch('config.apps.cash.google_iap.consume_google_purchase')
    @patch('config.apps.cash.google_iap.verify_google_purchase')
    @patch('config.apps.cash.google_iap.verify_pubsub_oidc_token')
    def test_rtdn_processes_purchase_once(
        self,
        mock_auth,
        mock_verify,
        mock_consume,
    ):
        mock_auth.return_value = {'email': 'pubsub@example.iam.gserviceaccount.com'}
        mock_verify.return_value = verified_purchase(
            self.user,
            token='rtdn-token',
            order_id='GPA.rtdn',
        )

        first = process_google_notification(
            self._envelope(),
            authorization='Bearer oidc-token',
        )
        second = process_google_notification(
            self._envelope(),
            authorization='Bearer oidc-token',
        )

        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(GooglePlayWebhookEvent.objects.count(), 1)
        self.assertEqual(PurchaseHistory.objects.count(), 1)
        mock_consume.assert_called_once()

    @patch('config.apps.cash.google_iap.verify_pubsub_oidc_token')
    def test_invalid_payload_is_failed_without_purchase(self, mock_auth):
        mock_auth.return_value = {}
        envelope = {'message': {'messageId': 'bad', 'data': 'not-base64'}}

        with self.assertRaises(GoogleIAPVerificationError):
            process_google_notification(
                envelope,
                authorization='Bearer oidc-token',
            )

        self.assertEqual(
            GooglePlayWebhookEvent.objects.get().status,
            GooglePlayWebhookEvent.Status.FAILED,
        )
        self.assertFalse(PurchaseHistory.objects.exists())

    @patch('config.apps.cash.google_iap.id_token.verify_oauth2_token')
    def test_pubsub_oidc_requires_expected_issuer_and_service_account(
        self,
        mock_verify,
    ):
        mock_verify.return_value = {
            'iss': 'https://accounts.google.com',
            'email': 'pubsub@example.iam.gserviceaccount.com',
            'email_verified': True,
        }

        claims = verify_pubsub_oidc_token('Bearer signed-token')

        self.assertEqual(
            claims['email'],
            'pubsub@example.iam.gserviceaccount.com',
        )
        mock_verify.assert_called_once()

    @patch('config.apps.cash.google_iap.verify_pubsub_oidc_token')
    def test_rtdn_rejects_wrong_package_name(self, mock_auth):
        mock_auth.return_value = {}
        envelope = self._envelope(message_id='wrong-package')
        payload = {
            'packageName': 'com.example.attacker',
            'oneTimeProductNotification': {
                'notificationType': 1,
                'productId': 'cash_1000',
                'purchaseToken': 'token',
            },
        }
        envelope['message']['data'] = base64.b64encode(
            json.dumps(payload).encode('utf-8')
        ).decode('ascii')

        with self.assertRaises(GoogleIAPVerificationError):
            process_google_notification(
                envelope,
                authorization='Bearer oidc-token',
            )

        self.assertFalse(PurchaseHistory.objects.exists())

    def test_voided_purchase_removes_cash_and_records_debt_once(self):
        self.user.cash = 400
        self.user.save(update_fields=['cash'])
        purchase = PurchaseHistory.objects.create(
            user=self.user,
            platform='google',
            transaction_id='GPA.voided',
            product_id='cash_1000',
            purchase_date=timezone.now(),
            purchased_cash=1000,
            paid_amount=1200,
            fee_deducted_amount=840,
            remaining_cash=1000,
        )
        GooglePlayPurchase.objects.create(
            purchase_history=purchase,
            purchase_token='voided-token',
            order_id='GPA.voided',
            obfuscated_external_account_id=self.user.google_play_account_token,
            purchase_state='PURCHASED',
            acknowledgement_state='ACKNOWLEDGED',
            consumption_state='CONSUMED',
            last_verified_at=timezone.now(),
            consumed_at=timezone.now(),
        )

        first = apply_google_voided_purchase({'purchaseToken': 'voided-token'})
        second = apply_google_voided_purchase({'purchaseToken': 'voided-token'})

        self.assertEqual(first, 'refunded')
        self.assertEqual(second, 'already_refunded')
        self.user.refresh_from_db()
        purchase.refresh_from_db()
        self.assertEqual((self.user.cash, self.user.cash_debt), (0, 600))
        self.assertTrue(purchase.is_refunded)
        self.assertEqual(purchase.refunded_cash, 1000)
        self.assertEqual(purchase.refund_debt, 600)

    @patch(
        'config.apps.cash.management.commands.sync_google_voided_purchases.list_google_voided_purchases',
        return_value=[],
    )
    def test_voided_purchase_sync_uses_30_day_then_24_hour_overlap(
        self,
        mock_list,
    ):
        before = timezone.now()
        call_command('sync_google_voided_purchases')
        first_window = mock_list.call_args.kwargs
        self.assertGreaterEqual(
            first_window['start_time'],
            before - timedelta(days=30, seconds=1),
        )

        state = GooglePlaySyncState.objects.get(key='voided_purchases')
        previous_checkpoint = timezone.now() - timedelta(days=2)
        state.last_synced_at = previous_checkpoint
        state.save(update_fields=['last_synced_at'])
        call_command('sync_google_voided_purchases')
        second_window = mock_list.call_args.kwargs
        self.assertEqual(
            second_window['start_time'],
            previous_checkpoint - timedelta(hours=24),
        )

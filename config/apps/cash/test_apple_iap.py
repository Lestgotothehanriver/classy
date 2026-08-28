import uuid
from types import SimpleNamespace
from unittest.mock import patch

from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.InAppOwnershipType import InAppOwnershipType
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Type import Type
from django.contrib.auth import get_user_model
from django.test import TestCase

from config.apps.cash.apple_iap import (
    AppleIAPConflictError,
    AppleIAPVerificationError,
    grant_apple_purchase,
    process_apple_notification,
    verify_apple_transaction,
)
from config.apps.cash.models import AppStoreWebhookEvent, PurchaseHistory
from config.apps.cash.tests import verified_transaction

User = get_user_model()


class AppleSignedTransactionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='signed-user', password='password', user_name='signed-user'
        )

    def _decoded(self, **overrides):
        values = {
            'transactionId': 'signed_tx_1',
            'originalTransactionId': 'signed_tx_1',
            'productId': 'cash_1000',
            'type': Type.CONSUMABLE,
            'quantity': 1,
            'inAppOwnershipType': InAppOwnershipType.PURCHASED,
            'appAccountToken': str(self.user.apple_app_account_token),
            'revocationDate': None,
            'environment': Environment.SANDBOX,
            'rawEnvironment': None,
            'purchaseDate': 1_750_000_000_000,
            'price': 1_200_000,
            'currency': 'KRW',
            'storefront': 'KOR',
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @patch('config.apps.cash.apple_iap._decode_signed_transaction')
    def test_signed_transaction_is_bound_to_product_and_user(self, mock_decode):
        mock_decode.return_value = self._decoded()

        verified = verify_apple_transaction(
            'header.payload.signature',
            expected_product_id='cash_1000',
            expected_app_account_token=self.user.apple_app_account_token,
        )

        self.assertEqual(verified.transaction_id, 'signed_tx_1')
        self.assertEqual(verified.price_milliunits, 1_200_000)
        self.assertEqual(verified.currency, 'KRW')

    @patch('config.apps.cash.apple_iap._decode_signed_transaction')
    def test_mismatched_app_account_token_is_rejected(self, mock_decode):
        mock_decode.return_value = self._decoded(appAccountToken=str(uuid.uuid4()))

        with self.assertRaises(AppleIAPVerificationError):
            verify_apple_transaction(
                'header.payload.signature',
                expected_product_id='cash_1000',
                expected_app_account_token=self.user.apple_app_account_token,
            )

    @patch('config.apps.cash.apple_iap._decode_signed_transaction')
    def test_non_consumable_transaction_is_rejected(self, mock_decode):
        mock_decode.return_value = self._decoded(type=Type.NON_CONSUMABLE)
        with self.assertRaises(AppleIAPVerificationError):
            verify_apple_transaction(
                'header.payload.signature',
                expected_product_id='cash_1000',
                expected_app_account_token=self.user.apple_app_account_token,
            )

    def test_transaction_cannot_be_replayed_by_another_user(self):
        grant_apple_purchase(
            self.user,
            verified_transaction(self.user, transaction_id='apple_tx_owned'),
        )
        other = User.objects.create_user(
            username='other', password='password', user_name='other'
        )

        with self.assertRaises(AppleIAPConflictError):
            grant_apple_purchase(
                other,
                verified_transaction(other, transaction_id='apple_tx_owned'),
            )

        other.refresh_from_db()
        self.assertEqual(other.cash, 0)


class AppleNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='refund-user', password='password', user_name='refund-user'
        )
        grant_apple_purchase(
            self.user,
            verified_transaction(self.user, transaction_id='refund_tx'),
        )

    def _verifier(self, notification_type, notification_uuid, percentage=100000):
        decoded_notification = SimpleNamespace(
            notificationUUID=str(notification_uuid),
            notificationType=notification_type,
            rawNotificationType=None,
            subtype=None,
            rawSubtype=None,
            signedDate=1_750_000_000_000,
            data=SimpleNamespace(signedTransactionInfo='signed-transaction'),
        )
        decoded_transaction = SimpleNamespace(
            transactionId='refund_tx',
            originalTransactionId='refund_tx',
            productId='cash_1000',
            appAccountToken=str(self.user.apple_app_account_token),
            environment=Environment.SANDBOX,
            rawEnvironment=None,
            purchaseDate=1_750_000_000_000,
            price=1_200_000,
            currency='KRW',
            storefront='KOR',
            revocationDate=1_750_000_000_000,
            revocationPercentage=percentage,
        )
        return SimpleNamespace(
            verify_and_decode_notification=lambda payload: decoded_notification,
            verify_and_decode_signed_transaction=lambda payload: decoded_transaction,
        )

    @patch('config.apps.cash.apple_iap.get_apple_signed_data_verifier')
    def test_refund_is_idempotent_and_records_spent_cash_as_debt(self, get_verifier):
        self.user.cash = 200
        self.user.save(update_fields=['cash'])
        get_verifier.return_value = self._verifier(
            NotificationTypeV2.REFUND, uuid.uuid4()
        )

        first = process_apple_notification('signed-refund-payload')
        second = process_apple_notification('signed-refund-payload')

        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.user.refresh_from_db()
        self.assertEqual((self.user.cash, self.user.cash_debt), (0, 800))
        purchase = PurchaseHistory.objects.get(transaction_id='refund_tx')
        self.assertTrue(purchase.is_refunded)
        self.assertEqual((purchase.refunded_cash, purchase.refund_debt), (1000, 800))
        self.assertEqual(AppStoreWebhookEvent.objects.count(), 1)

    @patch('config.apps.cash.apple_iap.get_apple_signed_data_verifier')
    def test_refund_reversed_restores_balance_and_releases_debt(self, get_verifier):
        self.user.cash = 200
        self.user.save(update_fields=['cash'])
        get_verifier.return_value = self._verifier(
            NotificationTypeV2.REFUND, uuid.uuid4()
        )
        process_apple_notification('signed-refund-payload')
        get_verifier.return_value = self._verifier(
            NotificationTypeV2.REFUND_REVERSED, uuid.uuid4()
        )

        process_apple_notification('signed-reversal-payload')

        self.user.refresh_from_db()
        self.assertEqual((self.user.cash, self.user.cash_debt), (200, 0))
        purchase = PurchaseHistory.objects.get(transaction_id='refund_tx')
        self.assertFalse(purchase.is_refunded)
        self.assertEqual((purchase.refunded_cash, purchase.refund_debt), (0, 0))

    @patch('config.apps.cash.apple_iap.get_apple_signed_data_verifier')
    def test_partial_refund_uses_apple_percentage(self, get_verifier):
        get_verifier.return_value = self._verifier(
            NotificationTypeV2.REFUND, uuid.uuid4(), percentage=50_000
        )

        process_apple_notification('signed-partial-refund')

        self.user.refresh_from_db()
        self.assertEqual((self.user.cash, self.user.cash_debt), (500, 0))
        purchase = PurchaseHistory.objects.get(transaction_id='refund_tx')
        self.assertEqual((purchase.refunded_cash, purchase.refund_percentage), (500, 50_000))

    @patch('config.apps.cash.apple_iap.get_apple_signed_data_verifier')
    def test_notification_uuid_cannot_be_reused_with_different_payload(
        self, get_verifier
    ):
        get_verifier.return_value = self._verifier(
            NotificationTypeV2.TEST, uuid.uuid4()
        )
        process_apple_notification('first-payload')

        with self.assertRaises(AppleIAPConflictError):
            process_apple_notification('different-payload')

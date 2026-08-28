"""StoreKit 2 purchase verification and App Store notification processing."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, load_pem_private_key
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from appstoreserverlibrary.api_client import AppStoreServerAPIClient
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.InAppOwnershipType import InAppOwnershipType
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Type import Type
from appstoreserverlibrary.signed_data_verifier import (
    SignedDataVerifier,
    VerificationException,
    VerificationStatus,
)

from .constants import PRODUCT_CASH_MAP, STORE_FEE_RATE
from .models import AppStoreWebhookEvent, PurchaseHistory

logger = logging.getLogger(__name__)


class AppleIAPError(Exception):
    """Base class for safe, user-facing Apple IAP failures."""


class AppleIAPConfigurationError(AppleIAPError):
    """The server is missing required App Store configuration."""


class AppleIAPVerificationError(AppleIAPError):
    """The signed transaction or notification is invalid."""


class AppleIAPTemporaryError(AppleIAPError):
    """Apple certificate status could not be checked temporarily."""


class AppleIAPConflictError(AppleIAPError):
    """A transaction conflicts with an already processed purchase."""


@dataclass(frozen=True)
class VerifiedAppleTransaction:
    transaction_id: str
    original_transaction_id: str
    product_id: str
    app_account_token: uuid.UUID
    environment: str
    purchase_date: datetime | None
    price_milliunits: int | None
    currency: str
    storefront: str
    revocation_date: datetime | None
    revocation_percentage: int


@dataclass(frozen=True)
class ApplePurchaseGrant:
    purchase: PurchaseHistory
    idempotent: bool
    credited_cash: int
    debt_offset: int


@dataclass(frozen=True)
class AppleNotificationResult:
    event: AppStoreWebhookEvent
    duplicate: bool


def _enum_value(value: Any, raw_value: Any = '') -> str:
    if value is not None and getattr(value, 'value', None) is not None:
        return str(value.value)
    return str(raw_value or '')


def _from_milliseconds(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=dt_timezone.utc)


def _configured_environment() -> Environment:
    raw = str(getattr(settings, 'APPLE_IAP_ENVIRONMENT', '')).upper()
    try:
        return {
            'SANDBOX': Environment.SANDBOX,
            'PRODUCTION': Environment.PRODUCTION,
        }[raw]
    except KeyError as exc:
        raise AppleIAPConfigurationError(
            'APPLE_IAP_ENVIRONMENT must be SANDBOX or PRODUCTION.'
        ) from exc


def _load_root_certificates(paths: tuple[str, ...]) -> list[bytes]:
    roots: list[bytes] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            raise AppleIAPConfigurationError(
                f'Apple root certificate is missing: {path.name}'
            )
        data = path.read_bytes()
        try:
            if b'-----BEGIN CERTIFICATE-----' in data:
                cert = x509.load_pem_x509_certificate(data)
                data = cert.public_bytes(Encoding.DER)
            else:
                x509.load_der_x509_certificate(data)
        except ValueError as exc:
            raise AppleIAPConfigurationError(
                f'Apple root certificate is invalid: {path.name}'
            ) from exc
        roots.append(data)
    if not roots:
        raise AppleIAPConfigurationError('No Apple root certificates are configured.')
    return roots


@lru_cache(maxsize=4)
def _cached_verifier(
    bundle_id: str,
    app_apple_id: int | None,
    environment: Environment,
    online_checks: bool,
    root_paths: tuple[str, ...],
) -> SignedDataVerifier:
    roots = _load_root_certificates(root_paths)
    return SignedDataVerifier(
        roots,
        online_checks,
        environment,
        bundle_id,
        app_apple_id,
    )


def get_apple_signed_data_verifier() -> SignedDataVerifier:
    bundle_id = str(getattr(settings, 'APPLE_BUNDLE_ID', '')).strip()
    if not bundle_id:
        raise AppleIAPConfigurationError('APPLE_BUNDLE_ID is not configured.')

    environment = _configured_environment()
    app_apple_id = getattr(settings, 'APPLE_APP_ID', None)
    if environment is Environment.PRODUCTION and not app_apple_id:
        raise AppleIAPConfigurationError(
            'APPLE_APP_ID is required for the production environment.'
        )

    root_paths = tuple(
        str(path) for path in getattr(settings, 'APPLE_IAP_ROOT_CERTIFICATES', ())
    )
    return _cached_verifier(
        bundle_id,
        app_apple_id,
        environment,
        bool(getattr(settings, 'APPLE_IAP_ENABLE_ONLINE_CHECKS', True)),
        root_paths,
    )


def _decode_signed_transaction(signed_transaction: str) -> Any:
    if not signed_transaction or len(signed_transaction) > 20000:
        raise AppleIAPVerificationError('Invalid signed transaction payload.')
    try:
        return get_apple_signed_data_verifier().verify_and_decode_signed_transaction(
            signed_transaction
        )
    except VerificationException as exc:
        status = getattr(exc, 'status', None)
        if status is VerificationStatus.RETRYABLE_VERIFICATION_FAILURE:
            raise AppleIAPTemporaryError(
                'Apple certificate status verification is temporarily unavailable.'
            ) from exc
        logger.warning('Apple transaction verification rejected status=%s', status)
        raise AppleIAPVerificationError('Apple transaction verification failed.') from exc


def verify_apple_transaction(
    signed_transaction: str,
    *,
    expected_product_id: str,
    expected_app_account_token: uuid.UUID,
) -> VerifiedAppleTransaction:
    """Verify StoreKit 2 JWS and bind it to a product and authenticated user."""

    decoded = _decode_signed_transaction(signed_transaction)

    if decoded.transactionId is None or decoded.originalTransactionId is None:
        raise AppleIAPVerificationError('Apple transaction identifier is missing.')
    if decoded.productId != expected_product_id:
        raise AppleIAPVerificationError('Apple product identifier mismatch.')
    if decoded.productId not in PRODUCT_CASH_MAP:
        raise AppleIAPVerificationError('Unknown Apple product identifier.')
    if decoded.type is not Type.CONSUMABLE:
        raise AppleIAPVerificationError('The Apple product is not consumable.')
    if decoded.quantity != 1:
        raise AppleIAPVerificationError('Invalid Apple purchase quantity.')
    if decoded.inAppOwnershipType not in (None, InAppOwnershipType.PURCHASED):
        raise AppleIAPVerificationError('Family-shared purchases are not supported.')

    try:
        app_account_token = uuid.UUID(str(decoded.appAccountToken))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppleIAPVerificationError('Apple app account token is missing.') from exc
    if app_account_token != expected_app_account_token:
        raise AppleIAPVerificationError('Apple app account token mismatch.')
    if decoded.revocationDate is not None:
        raise AppleIAPVerificationError('The Apple transaction has been revoked.')

    return VerifiedAppleTransaction(
        transaction_id=str(decoded.transactionId),
        original_transaction_id=str(decoded.originalTransactionId),
        product_id=str(decoded.productId),
        app_account_token=app_account_token,
        environment=_enum_value(decoded.environment, decoded.rawEnvironment),
        purchase_date=_from_milliseconds(decoded.purchaseDate),
        price_milliunits=decoded.price,
        currency=str(decoded.currency or ''),
        storefront=str(decoded.storefront or ''),
        revocation_date=None,
        revocation_percentage=0,
    )


def _existing_grant(
    purchase: PurchaseHistory,
    user_id: int,
    verified: VerifiedAppleTransaction,
) -> ApplePurchaseGrant:
    if (
        purchase.user_id != user_id
        or purchase.platform != 'apple'
        or purchase.product_id != verified.product_id
        or purchase.app_account_token != verified.app_account_token
    ):
        raise AppleIAPConflictError(
            'This Apple transaction belongs to another purchase.'
        )
    if purchase.is_refunded:
        raise AppleIAPConflictError('This Apple transaction was refunded.')
    return ApplePurchaseGrant(
        purchase=purchase,
        idempotent=True,
        credited_cash=0,
        debt_offset=0,
    )


def grant_apple_purchase(user: Any, verified: VerifiedAppleTransaction) -> ApplePurchaseGrant:
    """Atomically grant cash once for one verified Apple transaction."""

    product = PRODUCT_CASH_MAP[verified.product_id]
    purchased_cash = product['cash']
    paid_amount = product['krw']
    if verified.currency == 'KRW' and verified.price_milliunits is not None:
        paid_amount = verified.price_milliunits // 1000
    fee_deducted_amount = int(paid_amount * (1 - STORE_FEE_RATE))
    User = get_user_model()

    try:
        with transaction.atomic():
            existing = (
                PurchaseHistory.objects.select_for_update()
                .filter(transaction_id=verified.transaction_id)
                .first()
            )
            if existing:
                return _existing_grant(existing, user.pk, verified)

            locked_user = User.objects.select_for_update().get(pk=user.pk)
            debt_offset = min(locked_user.cash_debt, purchased_cash)
            credited_cash = purchased_cash - debt_offset
            locked_user.cash_debt -= debt_offset
            locked_user.cash += credited_cash
            locked_user.save(update_fields=['cash', 'cash_debt'])

            purchase = PurchaseHistory.objects.create(
                user=locked_user,
                platform='apple',
                transaction_id=verified.transaction_id,
                original_transaction_id=verified.original_transaction_id,
                product_id=verified.product_id,
                app_account_token=verified.app_account_token,
                environment=verified.environment,
                purchase_date=verified.purchase_date,
                price_milliunits=verified.price_milliunits,
                currency=verified.currency,
                storefront=verified.storefront,
                purchased_cash=purchased_cash,
                paid_amount=paid_amount,
                fee_deducted_amount=fee_deducted_amount,
                remaining_cash=locked_user.cash,
            )
            return ApplePurchaseGrant(
                purchase=purchase,
                idempotent=False,
                credited_cash=credited_cash,
                debt_offset=debt_offset,
            )
    except IntegrityError:
        # A concurrent request may have won the unique transaction race. The
        # failed atomic block has rolled back its balance update at this point.
        existing = PurchaseHistory.objects.filter(
            transaction_id=verified.transaction_id
        ).first()
        if existing:
            return _existing_grant(existing, user.pk, verified)
        raise


def _notification_transaction(signed_transaction: str) -> VerifiedAppleTransaction:
    decoded = _decode_signed_transaction(signed_transaction)
    if not decoded.transactionId or not decoded.productId:
        raise AppleIAPVerificationError('Notification transaction data is incomplete.')
    try:
        app_account_token = uuid.UUID(str(decoded.appAccountToken))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppleIAPVerificationError(
            'Notification app account token is missing.'
        ) from exc
    return VerifiedAppleTransaction(
        transaction_id=str(decoded.transactionId),
        original_transaction_id=str(decoded.originalTransactionId or ''),
        product_id=str(decoded.productId),
        app_account_token=app_account_token,
        environment=_enum_value(decoded.environment, decoded.rawEnvironment),
        purchase_date=_from_milliseconds(decoded.purchaseDate),
        price_milliunits=decoded.price,
        currency=str(decoded.currency or ''),
        storefront=str(decoded.storefront or ''),
        revocation_date=_from_milliseconds(decoded.revocationDate),
        revocation_percentage=min(max(decoded.revocationPercentage or 100000, 0), 100000),
    )


def _set_refund_target(
    verified: VerifiedAppleTransaction,
    target_percentage: int,
) -> tuple[PurchaseHistory | None, str]:
    User = get_user_model()
    purchase = (
        PurchaseHistory.objects.select_for_update()
        .filter(transaction_id=verified.transaction_id, platform='apple')
        .first()
    )
    if purchase is None:
        return None, 'purchase_not_found'
    if (
        purchase.product_id != verified.product_id
        or purchase.app_account_token != verified.app_account_token
    ):
        raise AppleIAPConflictError('Notification transaction does not match purchase.')

    target_percentage = min(max(target_percentage, 0), 100000)
    target_cash = math.ceil(purchase.purchased_cash * target_percentage / 100000)
    current_cash = purchase.refunded_cash
    locked_user = User.objects.select_for_update().get(pk=purchase.user_id)

    if target_cash > current_cash:
        delta = target_cash - current_cash
        recovered = min(locked_user.cash, delta)
        debt = delta - recovered
        locked_user.cash -= recovered
        locked_user.cash_debt += debt
        purchase.refund_debt += debt
    elif target_cash < current_cash:
        restore = current_cash - target_cash
        released_debt = min(purchase.refund_debt, restore, locked_user.cash_debt)
        locked_user.cash_debt -= released_debt
        purchase.refund_debt -= released_debt
        locked_user.cash += restore - released_debt

    locked_user.save(update_fields=['cash', 'cash_debt'])
    purchase.refunded_cash = target_cash
    purchase.refund_percentage = target_percentage
    purchase.is_refunded = target_cash > 0
    purchase.refunded_at = timezone.now() if target_cash > 0 else None
    purchase.save(
        update_fields=[
            'refunded_cash',
            'refund_percentage',
            'refund_debt',
            'is_refunded',
            'refunded_at',
        ]
    )
    return purchase, 'refund_applied' if target_cash > 0 else 'refund_reversed'


def process_apple_notification(signed_payload: str) -> AppleNotificationResult:
    """Verify and idempotently process an App Store Server Notification V2."""

    if not signed_payload or len(signed_payload) > 50000:
        raise AppleIAPVerificationError('Invalid signed notification payload.')
    try:
        decoded = get_apple_signed_data_verifier().verify_and_decode_notification(
            signed_payload
        )
    except VerificationException as exc:
        status = getattr(exc, 'status', None)
        if status is VerificationStatus.RETRYABLE_VERIFICATION_FAILURE:
            raise AppleIAPTemporaryError(
                'Apple notification verification is temporarily unavailable.'
            ) from exc
        logger.warning('Apple notification verification rejected status=%s', status)
        raise AppleIAPVerificationError('Apple notification verification failed.') from exc

    try:
        notification_uuid = uuid.UUID(str(decoded.notificationUUID))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AppleIAPVerificationError('Notification UUID is missing.') from exc

    notification_type = _enum_value(
        decoded.notificationType,
        decoded.rawNotificationType,
    )
    subtype = _enum_value(decoded.subtype, decoded.rawSubtype)
    payload_hash = hashlib.sha256(signed_payload.encode('utf-8')).hexdigest()

    with transaction.atomic():
        existing = (
            AppStoreWebhookEvent.objects.select_for_update()
            .filter(notification_uuid=notification_uuid)
            .first()
        )
        if existing:
            if existing.payload_sha256 != payload_hash:
                raise AppleIAPConflictError(
                    'Notification UUID was reused with a different payload.'
                )
            return AppleNotificationResult(event=existing, duplicate=True)

        event = AppStoreWebhookEvent.objects.create(
            notification_uuid=notification_uuid,
            notification_type=notification_type,
            subtype=subtype,
            payload_sha256=payload_hash,
            signed_at=_from_milliseconds(decoded.signedDate),
        )

        if decoded.notificationType is NotificationTypeV2.TEST:
            event.status = AppStoreWebhookEvent.Status.PROCESSED
            event.detail = 'test_notification'
        elif decoded.notificationType in {
            NotificationTypeV2.REFUND,
            NotificationTypeV2.REVOKE,
            NotificationTypeV2.REFUND_REVERSED,
        }:
            signed_transaction = getattr(decoded.data, 'signedTransactionInfo', None)
            if not signed_transaction:
                raise AppleIAPVerificationError(
                    'Notification transaction is missing.'
                )
            verified = _notification_transaction(signed_transaction)
            event.transaction_id = verified.transaction_id
            target = (
                0
                if decoded.notificationType is NotificationTypeV2.REFUND_REVERSED
                else verified.revocation_percentage
            )
            purchase, detail = _set_refund_target(verified, target)
            event.status = (
                AppStoreWebhookEvent.Status.PROCESSED
                if purchase is not None
                else AppStoreWebhookEvent.Status.IGNORED
            )
            event.detail = detail
        elif decoded.notificationType is NotificationTypeV2.REFUND_DECLINED:
            event.status = AppStoreWebhookEvent.Status.PROCESSED
            event.detail = 'refund_declined'
        else:
            event.status = AppStoreWebhookEvent.Status.IGNORED
            event.detail = 'notification_not_actionable'

        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                'transaction_id',
                'status',
                'detail',
                'processed_at',
            ]
        )
        return AppleNotificationResult(event=event, duplicate=False)


def _decode_private_key() -> bytes:
    encoded = str(getattr(settings, 'APPLE_IAP_PRIVATE_KEY_BASE64', '')).strip()
    if not encoded:
        raise AppleIAPConfigurationError(
            'APPLE_IAP_PRIVATE_KEY_BASE64 is not configured.'
        )
    if encoded.startswith('-----BEGIN PRIVATE KEY-----'):
        key = encoded.encode('utf-8')
    else:
        try:
            # Render/env managers may preserve line wrapping from the `base64`
            # CLI output. Whitespace is not part of the value, so normalize it
            # before strict decoding while still rejecting any other character.
            compact = ''.join(encoded.split())
            key = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise AppleIAPConfigurationError(
                'APPLE_IAP_PRIVATE_KEY_BASE64 is invalid.'
            ) from exc
    if b'-----BEGIN PRIVATE KEY-----' not in key:
        raise AppleIAPConfigurationError('The Apple IAP private key is invalid.')
    try:
        private_key = load_pem_private_key(key, password=None)
    except (TypeError, ValueError) as exc:
        raise AppleIAPConfigurationError(
            'The Apple IAP private key is invalid.'
        ) from exc
    if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(
        private_key.curve,
        ec.SECP256R1,
    ):
        raise AppleIAPConfigurationError(
            'The Apple IAP private key must use the P-256 curve.'
        )
    return key


def get_app_store_server_api_client() -> AppStoreServerAPIClient:
    key_id = str(getattr(settings, 'APPLE_IAP_KEY_ID', '')).strip()
    issuer_id = str(getattr(settings, 'APPLE_IAP_ISSUER_ID', '')).strip()
    bundle_id = str(getattr(settings, 'APPLE_BUNDLE_ID', '')).strip()
    if not key_id or not issuer_id or not bundle_id:
        raise AppleIAPConfigurationError(
            'Apple App Store Server API identifiers are incomplete.'
        )
    return AppStoreServerAPIClient(
        _decode_private_key(),
        key_id,
        issuer_id,
        bundle_id,
        _configured_environment(),
    )

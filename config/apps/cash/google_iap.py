"""Google Play Billing verification, granting, consumption, and reconciliation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token, service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .constants import GOOGLE_PRODUCT_CASH_MAP, STORE_FEE_RATE
from .models import (
    GooglePlayPurchase,
    GooglePlayWebhookEvent,
    PurchaseHistory,
)

logger = logging.getLogger(__name__)

ANDROID_PUBLISHER_SCOPE = 'https://www.googleapis.com/auth/androidpublisher'
PURCHASED_STATE = 0
CONSUMED_STATE = 1
ONE_TIME_PRODUCT_PURCHASED = 1


class GoogleIAPError(Exception):
    """Base class for safe Google IAP errors."""


class GoogleIAPConfigurationError(GoogleIAPError):
    """Raised when Google Play server credentials are incomplete or invalid."""


class GoogleIAPVerificationError(GoogleIAPError):
    """Raised when a purchase or RTDN payload cannot be trusted."""


class GoogleIAPConflictError(GoogleIAPError):
    """Raised when a purchase token is already owned by another purchase."""


class GoogleIAPTemporaryError(GoogleIAPError):
    """Raised when Google Play cannot currently complete an operation."""


@dataclass(frozen=True)
class VerifiedGooglePurchase:
    """Validated Google Play purchase facts used by the grant transaction."""

    purchase_token: str
    product_id: str
    order_id: str
    account_token: uuid.UUID
    purchase_time: datetime | None
    purchase_state: str
    acknowledgement_state: str
    consumption_state: str


@dataclass(frozen=True)
class GooglePurchaseGrant:
    """Result of an idempotent Google Play cash grant."""

    purchase: PurchaseHistory
    detail: GooglePlayPurchase
    idempotent: bool
    credited_cash: int
    debt_offset: int


@dataclass(frozen=True)
class GoogleNotificationResult:
    """Result returned to the Pub/Sub push endpoint."""

    event: GooglePlayWebhookEvent
    duplicate: bool


def _publisher_service():
    """Build an authenticated Android Publisher API client."""

    encoded = settings.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64
    if not encoded:
        raise GoogleIAPConfigurationError('Google Play credentials are not configured.')
    try:
        raw = base64.b64decode(encoded, validate=True)
        info = json.loads(raw.decode('utf-8'))
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=[ANDROID_PUBLISHER_SCOPE],
        )
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GoogleIAPConfigurationError('Google Play credentials are invalid.') from exc
    return build('androidpublisher', 'v3', credentials=credentials, cache_discovery=False)


def _execute_google(request, *, invalid_purchase_is_verification: bool = False):
    """Execute one Publisher request without leaking request tokens in errors."""

    try:
        return request.execute()
    except HttpError as exc:
        status_code = getattr(exc.resp, 'status', None)
        if invalid_purchase_is_verification and status_code in {400, 404, 410}:
            raise GoogleIAPVerificationError('Google Play purchase is invalid.') from exc
        if status_code in {401, 403}:
            raise GoogleIAPConfigurationError('Google Play API access is unavailable.') from exc
        raise GoogleIAPTemporaryError('Google Play API is temporarily unavailable.') from exc
    except GoogleIAPError:
        raise
    except Exception as exc:
        raise GoogleIAPTemporaryError('Google Play API is temporarily unavailable.') from exc


def _parse_account_token(value: Any) -> uuid.UUID:
    """Parse Google obfuscatedExternalAccountId as the app-issued UUID."""

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise GoogleIAPVerificationError(
            'Google Play account identifier is missing or invalid.'
        ) from exc


def verify_google_purchase(
    purchase_token: str,
    *,
    expected_product_id: str,
    expected_account_token: uuid.UUID | None,
) -> VerifiedGooglePurchase:
    """Fetch and validate a Google Play one-time product purchase."""

    if expected_product_id not in GOOGLE_PRODUCT_CASH_MAP:
        raise GoogleIAPVerificationError('Invalid Google Play product.')
    if not purchase_token:
        raise GoogleIAPVerificationError('Google Play purchase token is missing.')

    service = _publisher_service()
    response = _execute_google(
        service.purchases().products().get(
            packageName=settings.GOOGLE_PLAY_PACKAGE_NAME,
            productId=expected_product_id,
            token=purchase_token,
        ),
        invalid_purchase_is_verification=True,
    )

    if int(response.get('purchaseState', -1)) != PURCHASED_STATE:
        raise GoogleIAPVerificationError('Google Play purchase is not completed.')
    if int(response.get('quantity', 1)) != 1:
        raise GoogleIAPVerificationError('Google Play purchase quantity is invalid.')
    if int(response.get('consumptionState', 0)) == CONSUMED_STATE:
        raise GoogleIAPConflictError('Google Play purchase was already consumed.')

    account_token = _parse_account_token(
        response.get('obfuscatedExternalAccountId')
    )
    if expected_account_token is not None and account_token != expected_account_token:
        raise GoogleIAPConflictError(
            'Google Play purchase belongs to another account.'
        )

    purchase_time = None
    purchase_time_millis = response.get('purchaseTimeMillis')
    if purchase_time_millis is not None:
        try:
            purchase_time = datetime.fromtimestamp(
                int(purchase_time_millis) / 1000,
                tz=datetime_timezone.utc,
            )
        except (TypeError, ValueError, OSError) as exc:
            raise GoogleIAPVerificationError(
                'Google Play purchase time is invalid.'
            ) from exc

    return VerifiedGooglePurchase(
        purchase_token=purchase_token,
        product_id=expected_product_id,
        order_id=str(response.get('orderId') or ''),
        account_token=account_token,
        purchase_time=purchase_time,
        purchase_state='PURCHASED',
        acknowledgement_state=(
            'ACKNOWLEDGED'
            if int(response.get('acknowledgementState', 0)) == 1
            else 'NOT_ACKNOWLEDGED'
        ),
        consumption_state='NOT_CONSUMED',
    )


def _existing_grant(
    detail: GooglePlayPurchase,
    *,
    user_id: int,
    product_id: str,
) -> GooglePurchaseGrant:
    """Validate ownership and return an idempotent existing grant."""

    purchase = detail.purchase_history
    if (
        purchase.user_id != user_id
        or purchase.platform != 'google'
        or purchase.product_id != product_id
    ):
        raise GoogleIAPConflictError(
            'This Google Play purchase belongs to another purchase.'
        )
    if purchase.is_refunded:
        raise GoogleIAPConflictError('This Google Play purchase was refunded.')
    return GooglePurchaseGrant(
        purchase=purchase,
        detail=detail,
        idempotent=True,
        credited_cash=0,
        debt_offset=0,
    )


def grant_google_purchase(
    user: Any,
    verified: VerifiedGooglePurchase,
) -> GooglePurchaseGrant:
    """Atomically grant cash and create the Google-specific purchase detail."""

    product = GOOGLE_PRODUCT_CASH_MAP[verified.product_id]
    purchased_cash = product['cash']
    paid_amount = product['krw']
    transaction_id = verified.order_id or (
        f"google:{hashlib.sha256(verified.purchase_token.encode('utf-8')).hexdigest()}"
    )
    User = get_user_model()

    try:
        with transaction.atomic():
            existing = (
                GooglePlayPurchase.objects.select_for_update()
                .select_related('purchase_history')
                .filter(purchase_token=verified.purchase_token)
                .first()
            )
            if existing:
                return _existing_grant(
                    existing,
                    user_id=user.pk,
                    product_id=verified.product_id,
                )

            if PurchaseHistory.objects.filter(transaction_id=transaction_id).exists():
                raise GoogleIAPConflictError(
                    'This Google Play order belongs to another purchase.'
                )

            locked_user = User.objects.select_for_update().get(pk=user.pk)
            debt_offset = min(locked_user.cash_debt, purchased_cash)
            credited_cash = purchased_cash - debt_offset
            locked_user.cash_debt -= debt_offset
            locked_user.cash += credited_cash
            locked_user.save(update_fields=['cash', 'cash_debt'])

            purchase = PurchaseHistory.objects.create(
                user=locked_user,
                platform='google',
                transaction_id=transaction_id,
                product_id=verified.product_id,
                purchase_date=verified.purchase_time,
                purchased_cash=purchased_cash,
                paid_amount=paid_amount,
                fee_deducted_amount=int(paid_amount * (1 - STORE_FEE_RATE)),
                remaining_cash=locked_user.cash,
            )
            detail = GooglePlayPurchase.objects.create(
                purchase_history=purchase,
                purchase_token=verified.purchase_token,
                order_id=verified.order_id,
                obfuscated_external_account_id=verified.account_token,
                purchase_state=verified.purchase_state,
                acknowledgement_state=verified.acknowledgement_state,
                consumption_state=verified.consumption_state,
                last_verified_at=timezone.now(),
            )
            return GooglePurchaseGrant(
                purchase=purchase,
                detail=detail,
                idempotent=False,
                credited_cash=credited_cash,
                debt_offset=debt_offset,
            )
    except IntegrityError:
        existing = (
            GooglePlayPurchase.objects.select_related('purchase_history')
            .filter(purchase_token=verified.purchase_token)
            .first()
        )
        if existing:
            return _existing_grant(
                existing,
                user_id=user.pk,
                product_id=verified.product_id,
            )
        raise


def consume_google_purchase(detail: GooglePlayPurchase) -> None:
    """Consume one granted Google Play purchase and persist completion."""

    if detail.consumption_state == 'CONSUMED':
        return
    service = _publisher_service()
    _execute_google(
        service.purchases().products().consume(
            packageName=settings.GOOGLE_PLAY_PACKAGE_NAME,
            productId=detail.purchase_history.product_id,
            token=detail.purchase_token,
        )
    )
    now = timezone.now()
    GooglePlayPurchase.objects.filter(pk=detail.pk).update(
        consumption_state='CONSUMED',
        consumed_at=now,
        last_verified_at=now,
    )
    detail.consumption_state = 'CONSUMED'
    detail.consumed_at = now


def process_google_purchase(user: Any, product_id: str, purchase_token: str) -> GooglePurchaseGrant:
    """Verify, grant once, and server-consume a Google Play purchase."""

    existing = (
        GooglePlayPurchase.objects.select_related('purchase_history')
        .filter(purchase_token=purchase_token)
        .first()
    )
    if existing:
        grant = _existing_grant(existing, user_id=user.pk, product_id=product_id)
        if existing.consumption_state == 'CONSUMED':
            return grant
    else:
        verified = verify_google_purchase(
            purchase_token,
            expected_product_id=product_id,
            expected_account_token=user.google_play_account_token,
        )
        grant = grant_google_purchase(user, verified)

    # Consumption deliberately occurs after the grant transaction commits. A
    # transient failure therefore leaves an idempotent record for a safe retry.
    consume_google_purchase(grant.detail)
    return grant


def verify_pubsub_oidc_token(authorization: str) -> dict[str, Any]:
    """Verify the Google-signed OIDC token attached to a Pub/Sub push."""

    audience = settings.GOOGLE_PLAY_RTDN_AUDIENCE
    expected_email = settings.GOOGLE_PLAY_RTDN_SERVICE_ACCOUNT_EMAIL
    if not audience or not expected_email:
        raise GoogleIAPConfigurationError('Google Play RTDN authentication is not configured.')
    scheme, separator, token = authorization.partition(' ')
    if separator != ' ' or scheme.lower() != 'bearer' or not token:
        raise GoogleIAPVerificationError('Missing Pub/Sub bearer token.')
    try:
        claims = id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            audience=audience,
        )
    except Exception as exc:
        raise GoogleIAPVerificationError('Invalid Pub/Sub bearer token.') from exc

    if claims.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}:
        raise GoogleIAPVerificationError('Invalid Pub/Sub token issuer.')
    if claims.get('email') != expected_email or claims.get('email_verified') not in {True, 'true'}:
        raise GoogleIAPVerificationError('Invalid Pub/Sub service account.')
    return claims


def process_google_notification(
    envelope: dict[str, Any],
    *,
    authorization: str,
) -> GoogleNotificationResult:
    """Authenticate and process one Google Play RTDN Pub/Sub envelope."""

    verify_pubsub_oidc_token(authorization)
    message = envelope.get('message') if isinstance(envelope, dict) else None
    if not isinstance(message, dict):
        raise GoogleIAPVerificationError('Invalid Pub/Sub envelope.')
    message_id = str(message.get('messageId') or message.get('message_id') or '')
    if not message_id:
        raise GoogleIAPVerificationError('Pub/Sub messageId is required.')

    duplicate = False
    try:
        with transaction.atomic():
            event = GooglePlayWebhookEvent.objects.create(message_id=message_id)
    except IntegrityError:
        event = GooglePlayWebhookEvent.objects.get(message_id=message_id)
        duplicate = True
        if event.status != GooglePlayWebhookEvent.Status.FAILED:
            return GoogleNotificationResult(event=event, duplicate=True)

    try:
        encoded_data = message.get('data')
        if not isinstance(encoded_data, str):
            raise GoogleIAPVerificationError('Pub/Sub message data is required.')
        try:
            decoded_data = base64.b64decode(encoded_data, validate=True)
            payload = json.loads(decoded_data.decode('utf-8'))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GoogleIAPVerificationError('Invalid Google Play RTDN payload.') from exc

        if payload.get('packageName') != settings.GOOGLE_PLAY_PACKAGE_NAME:
            raise GoogleIAPVerificationError('Google Play package name does not match.')
        notification = payload.get('oneTimeProductNotification')
        if not isinstance(notification, dict):
            event.status = GooglePlayWebhookEvent.Status.IGNORED
            event.detail = 'unsupported_notification'
        else:
            notification_type = int(notification.get('notificationType', 0))
            product_id = str(
                notification.get('productId') or notification.get('sku') or ''
            )
            purchase_token = str(notification.get('purchaseToken') or '')
            event.notification_type = notification_type
            event.product_id = product_id
            event.purchase_token_sha256 = hashlib.sha256(
                purchase_token.encode('utf-8')
            ).hexdigest() if purchase_token else ''

            if notification_type != ONE_TIME_PRODUCT_PURCHASED:
                event.status = GooglePlayWebhookEvent.Status.IGNORED
                event.detail = 'not_a_completed_purchase'
            else:
                verified = verify_google_purchase(
                    purchase_token,
                    expected_product_id=product_id,
                    expected_account_token=None,
                )
                User = get_user_model()
                user = User.objects.filter(
                    google_play_account_token=verified.account_token
                ).first()
                if user is None:
                    raise GoogleIAPConflictError(
                        'Google Play purchase account is unknown.'
                    )
                grant = grant_google_purchase(user, verified)
                consume_google_purchase(grant.detail)
                event.status = GooglePlayWebhookEvent.Status.PROCESSED
                event.detail = 'purchase_processed'
        event.processed_at = timezone.now()
        event.save(update_fields=[
            'notification_type', 'product_id', 'purchase_token_sha256',
            'status', 'detail', 'processed_at',
        ])
        return GoogleNotificationResult(event=event, duplicate=duplicate)
    except Exception:
        event.status = GooglePlayWebhookEvent.Status.FAILED
        event.detail = 'processing_failed'
        event.processed_at = timezone.now()
        event.save(update_fields=['status', 'detail', 'processed_at'])
        raise


def list_google_voided_purchases(
    *,
    start_time: datetime,
    end_time: datetime,
) -> Iterable[dict[str, Any]]:
    """Yield all voided purchases in a bounded reconciliation window."""

    service = _publisher_service()
    page_token = None
    while True:
        request = service.purchases().voidedpurchases().list(
            packageName=settings.GOOGLE_PLAY_PACKAGE_NAME,
            startTime=str(int(start_time.timestamp() * 1000)),
            endTime=str(int(end_time.timestamp() * 1000)),
            type=0,
            includeQuantityBasedPartialRefund=False,
            token=page_token,
        )
        response = _execute_google(request)
        yield from response.get('voidedPurchases', [])
        page_token = (response.get('tokenPagination') or {}).get('nextPageToken')
        if not page_token:
            break


def apply_google_voided_purchase(voided: dict[str, Any]) -> str:
    """Reverse one Google grant exactly once, recording any cash shortfall as debt."""

    purchase_token = str(voided.get('purchaseToken') or '')
    order_id = str(voided.get('orderId') or '')
    if not purchase_token and not order_id:
        return 'invalid'

    User = get_user_model()
    with transaction.atomic():
        details = GooglePlayPurchase.objects.select_for_update().select_related(
            'purchase_history'
        )
        detail = details.filter(purchase_token=purchase_token).first() if purchase_token else None
        if detail is None and order_id:
            detail = details.filter(order_id=order_id).first()
        if detail is None:
            return 'purchase_not_found'

        purchase = PurchaseHistory.objects.select_for_update().get(
            pk=detail.purchase_history_id
        )
        if purchase.is_refunded:
            return 'already_refunded'

        user = User.objects.select_for_update().get(pk=purchase.user_id)
        recovered_cash = min(user.cash, purchase.purchased_cash)
        refund_debt = purchase.purchased_cash - recovered_cash
        user.cash -= recovered_cash
        user.cash_debt += refund_debt
        user.save(update_fields=['cash', 'cash_debt'])

        purchase.is_refunded = True
        purchase.refunded_at = timezone.now()
        purchase.refund_percentage = 100000
        purchase.refunded_cash = purchase.purchased_cash
        purchase.refund_debt = refund_debt
        purchase.save(update_fields=[
            'is_refunded', 'refunded_at', 'refund_percentage',
            'refunded_cash', 'refund_debt',
        ])
        return 'refunded'

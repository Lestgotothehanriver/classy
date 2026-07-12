import logging
import json

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from config.throttles import PurchaseRateThrottle

from datetime import timedelta
from django.utils import timezone

from .serializers import (
    CashPurchaseSerializer,
    LectureRentalSerializer,
    RedeemCouponSerializer,
)
from .models import PurchaseHistory, LectureRentalHistory, Account, Coupon
from config.apps.lecture.models import Lecture

logger = logging.getLogger(__name__)


class TossVirtualAccountWebhookView(APIView):
    """토스 DEPOSIT_CALLBACK을 검증하고 중복 없이 결제 상태를 반영한다."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from config.apps.tutoring.models import (
            CommissionInvoice,
            TossWebhookEvent,
            VirtualAccountPayment,
        )
        from config.apps.tutoring.registration_services import webhook_secret_matches

        payload = request.data
        event = payload.get("data", payload) if isinstance(payload, dict) else {}
        order_id = event.get("orderId")
        transaction_key = event.get("transactionKey")
        event_status = event.get("status")
        supplied_secret = event.get("secret")
        if not all([order_id, transaction_key, event_status, supplied_secret]):
            return Response(
                {"detail": "필수 웹훅 필드가 누락되었습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if event_status not in {
            "DONE",
            "WAITING_FOR_DEPOSIT",
            "CANCELED",
            "PARTIAL_CANCELED",
            "EXPIRED",
            "ABORTED",
        }:
            return Response(
                {"detail": "지원하지 않는 결제 상태입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            payment = VirtualAccountPayment.objects.select_for_update().filter(
                order_id=order_id
            ).first()
            if payment is None:
                return Response(
                    {"detail": "결제 주문을 찾을 수 없습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not webhook_secret_matches(payment, supplied_secret):
                return Response(
                    {"detail": "유효하지 않은 웹훅 secret입니다."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if TossWebhookEvent.objects.filter(
                transaction_key=transaction_key
            ).exists():
                return Response({"processed": False, "duplicate": True})

            try:
                with transaction.atomic():
                    TossWebhookEvent.objects.create(
                        transaction_key=transaction_key,
                        order_id=order_id,
                        event_status=event_status,
                        payload=payload,
                    )
            except IntegrityError:
                return Response({"processed": False, "duplicate": True})

            invoice = payment.invoice
            now = timezone.now()
            if event_status == "DONE":
                payment.fee_payment_status = (
                    VirtualAccountPayment.FeePaymentStatus.DONE
                )
                invoice.status = CommissionInvoice.Status.PAID
                invoice.paid_at = now
            elif event_status == "WAITING_FOR_DEPOSIT":
                payment.fee_payment_status = (
                    VirtualAccountPayment.FeePaymentStatus.WAITING_FOR_DEPOSIT
                )
                invoice.status = CommissionInvoice.Status.PAYMENT_PENDING
                invoice.paid_at = None
            elif event_status in {"CANCELED", "PARTIAL_CANCELED"}:
                payment.fee_payment_status = (
                    VirtualAccountPayment.FeePaymentStatus.CANCELLED
                )
                invoice.status = CommissionInvoice.Status.CANCELLED
                invoice.paid_at = None
            elif event_status == "EXPIRED":
                payment.fee_payment_status = (
                    VirtualAccountPayment.FeePaymentStatus.EXPIRED
                )
                invoice.status = CommissionInvoice.Status.FAILED
                invoice.paid_at = None
            elif event_status == "ABORTED":
                payment.fee_payment_status = (
                    VirtualAccountPayment.FeePaymentStatus.FAILED
                )
                invoice.status = CommissionInvoice.Status.FAILED
                invoice.paid_at = None
            payment.toss_response = payload
            payment.save(
                update_fields=["fee_payment_status", "toss_response", "updated_at"]
            )
            invoice.save(update_fields=["status", "paid_at", "updated_at"])

        return Response({"processed": True, "duplicate": False})

# ──────────────────────────────────────────────
# 상품 매핑 (Store product_id → 캐시 / 원화)
# ──────────────────────────────────────────────
PRODUCT_CASH_MAP = {
    'cash_100':   {'cash': 100,   'krw': 100},
    'cash_500':   {'cash': 500,   'krw': 500},
    'cash_1000':  {'cash': 1000,  'krw': 1000},
    'cash_5000':  {'cash': 5000,  'krw': 5000},
    'cash_10000': {'cash': 10000, 'krw': 10000},
    'cash_50000': {'cash': 50000, 'krw': 50000},
}

# 수수료율 (Apple/Google 기본 30%)
STORE_FEE_RATE = 0.30


# PurchaseRateThrottle is imported from config.throttles


# ──────────────────────────────────────────────
# Apple App Store 영수증 검증
# ──────────────────────────────────────────────
def verify_apple_receipt(receipt_data: str, expected_product_id: str) -> tuple:
    """
    Apple verifyReceipt API를 호출하여 영수증을 검증합니다.
    
    Args:
        receipt_data (str): iOS 클라이언트에서 전달받은 Base64 인코딩된 영수증 문자열.

    Apple 권장 흐름:
      1. Production URL로 먼저 요청
      2. status 21007 → Sandbox URL로 재시도

    Apple verifyReceipt API 응답 예시:
    {
    "status": 0,
    "environment": "Production",
    "receipt": {
        "bundle_id": "com.example.app",
        "in_app": [
        {
            "product_id": "cash_5000",
            "transaction_id": "1000001234567890",
            "original_transaction_id": "1000001234567890",
            "purchase_date": "2026-03-09 10:10:10 Etc/GMT",
            "quantity": "1"
        }
        ]
    }
    }
    
    Returns:
        (is_valid: bool, transaction_id: str | None, error_msg: str)
    """
    shared_secret = getattr(settings, 'APPLE_IAP_SHARED_SECRET', None)
    # App Store Connect shared secret = 애플 구독 영수증 검증할 때 서버 인증용 비밀번호
    if not shared_secret:
        logger.error("APPLE_IAP_SHARED_SECRET is not configured.")
        return False, None, "Server configuration error."

    payload = {
        'receipt-data': receipt_data,
        'password': shared_secret,
        'exclude-old-transactions': True,
    }

    production_url = 'https://buy.itunes.apple.com/verifyReceipt'
    sandbox_url = 'https://sandbox.itunes.apple.com/verifyReceipt'

    try:
        # 1) Production 먼저 시도
        resp = requests.post(production_url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # 2) 21007이면 Sandbox 재시도 (테스트/TestFlight 빌드)
        if data.get('status') == 21007:
            resp = requests.post(sandbox_url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        receipt_status = data.get('status')
        if receipt_status != 0:
            logger.warning("Apple receipt invalid. status=%s", receipt_status)
            return False, None, f"Invalid receipt (status={receipt_status})."

        # 3) in_app 배열에서 해당 product_id의 가장 최근 트랜잭션 탐색
        in_app = data.get('receipt', {}).get('in_app', [])
        if not in_app:
            # latest_receipt_info 도 확인 (구독이 아닌 소모성 상품은 in_app에 들어감)
            in_app = data.get('latest_receipt_info', [])

        matched_tx = None
        for item in reversed(in_app):  # 최신 것부터
            if item.get('product_id') == expected_product_id:
                matched_tx = item
                break

        if not matched_tx:
            return False, None, "Product not found in receipt."

        transaction_id = matched_tx.get('transaction_id')
        if not transaction_id:
            return False, None, "Missing transaction_id in receipt."

        # 4) bundle_id 검증 (위조 방지)
        expected_bundle = getattr(settings, 'APPLE_BUNDLE_ID', None)
        receipt_bundle = data.get('receipt', {}).get('bundle_id')
        if expected_bundle and receipt_bundle != expected_bundle:
            logger.warning(
                "Apple bundle_id mismatch: expected=%s got=%s",
                expected_bundle, receipt_bundle
            )
            return False, None, "Bundle ID mismatch."

        return True, transaction_id, ""

    except requests.RequestException as e:
        logger.exception("Apple verification network error: %s", e)
        return False, None, "Failed to connect to Apple verification server."
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.exception("Apple response parsing error: %s", e)
        return False, None, "Invalid response from Apple server."


# ──────────────────────────────────────────────
# Google Play Store 구매 토큰 검증
# ──────────────────────────────────────────────
def verify_google_receipt(purchase_token: str, product_id: str) -> tuple:
    """
    Google Play Developer API (androidpublisher v3)를 사용하여 
    인앱 상품 구매를 검증합니다.
    
    사전 설정:
      - GOOGLE_PLAY_SERVICE_ACCOUNT_JSON: 서비스 계정 JSON 파일 경로
      - ANDROID_PACKAGE_NAME: 앱의 패키지명
      
    Google Play Store API 응답 예시:
    {
    "purchaseState": 0,
    "orderId": "GPA.1234-5678-9012-34567",
    "productId": "cash_5000",
    "purchaseTimeMillis": "1710000000000",
    "acknowledgementState": 1
    }

    Returns:
        (is_valid: bool, transaction_id: str | None, error_msg: str)
    """
    service_account_json_str = getattr(settings, 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON', None)
    package_name = getattr(settings, 'ANDROID_PACKAGE_NAME', None)

    if not service_account_json_str or not package_name:
        logger.error(
            "Google Play settings missing. "
            "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON is not set or ANDROID_PACKAGE_NAME=%s",
            package_name
        )
        return False, None, "Server configuration error."

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        service_account_info = json.loads(service_account_json_str)

        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/androidpublisher'],
        )
        service = build('androidpublisher', 'v3', credentials=credentials, cache_discovery=False)

        result = service.purchases().products().get(
            packageName=package_name,
            productId=product_id,
            token=purchase_token,
        ).execute()

        # purchaseState: 0=구매완료, 1=취소됨, 2=보류중
        purchase_state = result.get('purchaseState')
        if purchase_state != 0:
            logger.warning(
                "Google purchase not completed. purchaseState=%s, token=%s",
                purchase_state, purchase_token[:20]
            )
            return False, None, f"Purchase not completed (state={purchase_state})."

        # orderId를 transaction_id로 사용 (고유하며 Google 대시보드와 매칭됨)
        order_id = result.get('orderId')
        if not order_id:
            return False, None, "Missing orderId from Google."

        return True, order_id, ""

    except json.JSONDecodeError:
        logger.exception("Google service account JSON is invalid.")
        return False, None, "Server configuration error."
    except ImportError:
        logger.exception("google-api-python-client is not installed.")
        return False, None, "Server configuration error."
    except Exception as e:
        logger.exception("Google Play verification failed: %s", e)
        return False, None, "Failed to verify with Google Play."


# ──────────────────────────────────────────────
# 강사 정산 계좌 API
# ──────────────────────────────────────────────

class InstructorAccountView(APIView):
    """
    URL: /cash/account/

    강사가 자신의 '정산 계좌 정보(Account)'를 조회, 등록, 수정하는 API View입니다.

    GET 요청 시 현재 강사에게 등록된 본인의 정산 계좌 정보를 조회합니다. 등록 정보가 없으면 404를 반환합니다.
    POST 요청 시 새로운 계좌 정보를 등록하거나 기존 계좌를 덮어씁니다. 강사 프로필(instructor_profile)이 있는 사용자만 이 기능을 사용할 수 있습니다.

    Request Body (POST):
        bank (str): 은행명 (예: '국민은행').
        account_number (str): 계좌번호.
        account_holder (str): 예금주명.

    Returns:
        Response (GET): {
            "bank": str,
            "account_number": str,
            "account_holder": str
        }
        Response (POST): {
            "bank": str,
            "account_number": str,
            "account_holder": str
        }
    """
    permission_classes = [IsAuthenticated]

    def _get_instructor(self, user):
        return getattr(user, 'instructor_profile', None)

    def get(self, request):
        instructor = self._get_instructor(request.user)
        if not instructor:
            return Response({'detail': 'Instructor profile required.'}, status=403)
        try:
            acct = instructor.account
            return Response({
                'bank': acct.bank,
                'account_number': acct.account_number,
                'account_holder': acct.account_holder,
            })
        except Account.DoesNotExist:
            return Response({'detail': 'No account registered.'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        instructor = self._get_instructor(request.user)
        if not instructor:
            return Response({'detail': 'Instructor profile required.'}, status=403)

        bank = (request.data.get('bank') or '').strip()
        account_number = (request.data.get('account_number') or '').strip()
        account_holder = (request.data.get('account_holder') or '').strip()

        if not all([bank, account_number, account_holder]):
            return Response(
                {'detail': 'bank, account_number, account_holder are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        acct, created = Account.objects.get_or_create(
            instructor=instructor,
            defaults={
                'bank': bank,
                'account_number': account_number,
                'account_holder': account_holder,
            },
        )
        if not created:
            acct.bank = bank
            acct.account_number = account_number
            acct.account_holder = account_holder
            acct.save(update_fields=['bank', 'account_number', 'account_holder'])

        return Response({
            'bank': acct.bank,
            'account_number': acct.account_number,
            'account_holder': acct.account_holder,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ──────────────────────────────────────────────
# 캐시 구매 API
# ──────────────────────────────────────────────
class PurchaseCashView(APIView):
    """
    URL: /cash/purchase/

    인앱 결제(Apple/Google) 영수증을 검증하고, 성공 시 유저에게 '캐시(Cash)'를 적립하는 API View입니다.

    POST 요청 시 전달받은 인앱 결제 영수증 데이터를 각각 Apple verifyReceipt API 혹은 Google Play API를 통해 검증합니다.
    영수증 검증이 통과되면, 중복 결제를 방지하기 위해 unique 트랜잭션 ID 여부를 검사하고, 트랜잭션 내에서 유저의 캐시 컬럼을 동시성 락(select_for_update) 하에 원자적으로 차감/증가 처리한 후 구매 내역을 생성합니다.

    Request Body:
        platform (str): 결제 플랫폼 ('apple' | 'google').
        product_id (str): 결제 상품 ID (예: 'cash_5000').
        receipt_data (str, optional): Apple 영수증 Base64 데이터.
        purchase_token (str, optional): Google 구매 토큰.

    Returns:
        Response: {
            "message": "Cash purchased successfully",
            "purchased_cash": int,
            "remaining_cash": int
        }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [PurchaseRateThrottle]

    def post(self, request):
        serializer = CashPurchaseSerializer(data=request.data)
        logger.debug("[BACKEND_DEBUG_CASH] PurchaseCash Attempt - data: %s", request.data)
        if not serializer.is_valid():
            logger.warning("[BACKEND_DEBUG_CASH] PurchaseCash Validation FAILED - errors: %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        platform = serializer.validated_data['platform']
        product_id = serializer.validated_data['product_id']

        # ── 1. 상품 유효성 ─────────────────────────
        product_info = PRODUCT_CASH_MAP.get(product_id)
        if not product_info:
            return Response(
                {"error": "Invalid product_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        purchased_cash = product_info['cash']
        paid_amount = product_info['krw']
        fee_deducted_amount = int(paid_amount * (1 - STORE_FEE_RATE))

        # ── 2. 플랫폼별 영수증 검증 ──────────────────
        if platform == 'apple':
            receipt_data = serializer.validated_data['receipt_data']
            is_valid, transaction_id, error_msg = verify_apple_receipt(receipt_data, product_id)
        else:  # google
            purchase_token = serializer.validated_data['purchase_token']
            is_valid, transaction_id, error_msg = verify_google_receipt(purchase_token, product_id)

        if not is_valid:
            logger.warning(
                "Purchase verification failed. user=%s platform=%s error=%s",
                request.user.pk, platform, error_msg,
            )
            return Response(
                {"error": f"{platform.capitalize()} verification failed: {error_msg}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 3. 중복 결제 방지 (DB unique 제약 + 코드 레벨 체크) ──
        if PurchaseHistory.objects.filter(transaction_id=transaction_id).exists():
            logger.warning(
                "Duplicate transaction attempt. user=%s tx_id=%s",
                request.user.pk, transaction_id,
            )
            return Response(
                {"error": "This transaction has already been processed."},
                status=status.HTTP_409_CONFLICT,
            )

        # ── 4. Atomic Block: 캐시 적립 + 내역 생성 ──────
        #    select_for_update()로 동시 요청 시 Race Condition 방지
        try:
            with transaction.atomic():
                from django.contrib.auth import get_user_model
                User = get_user_model()

                user = User.objects.select_for_update().get(pk=request.user.pk)
                user.cash = F('cash') + purchased_cash
                user.save(update_fields=['cash'])

                # save() 후 F() expression이므로 refresh 필요
                user.refresh_from_db()

                PurchaseHistory.objects.create(
                    user=user,
                    platform=platform,
                    transaction_id=transaction_id,
                    purchased_cash=purchased_cash,
                    paid_amount=paid_amount,
                    fee_deducted_amount=fee_deducted_amount,
                    remaining_cash=user.cash,
                )

        except Exception as e:
            logger.exception(
                "Failed to process purchase. user=%s tx_id=%s error=%s",
                request.user.pk, transaction_id, e,
            )
            return Response(
                {"error": "Internal server error while processing purchase."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.debug("[BACKEND_DEBUG_CASH] Purchase SUCCESS - user: %s, product: %s, cash: %d, tx: %s",
            user.pk, product_id, purchased_cash, transaction_id)

        return Response({
            "message": "Cash purchased successfully",
            "purchased_cash": purchased_cash,
            "remaining_cash": user.cash,
        }, status=status.HTTP_200_OK)


class RedeemCouponView(APIView):
    """
    URL: /cash/coupons/redeem/

    프로모션 '쿠폰(Coupon)' 코드를 입력받아 캐시를 충전해주는 API View입니다.

    POST 요청 시 쿠폰 코드를 입력받아 활성화 여부, 기사용 여부, 만료 여부를 트랜잭션 하에서 원자적으로 검증합니다.
    검증 결과 쿠폰이 유효한 경우 해당 쿠폰에 명시된 금액(cash_amount)만큼 유저에게 캐시를 즉시 적립하고 쿠폰 사용 내역을 갱신합니다.

    Request Body:
        code (str): 사용할 쿠폰 코드.

    Returns:
        Response: {
            "message": "Coupon redeemed successfully.",
            "redeemed_cash": int,
            "remaining_cash": int
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RedeemCouponSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code'].strip()
        now = timezone.now()

        try:
            with transaction.atomic():
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.select_for_update().get(pk=request.user.pk)
                coupon = Coupon.objects.select_for_update().filter(code=code).first()

                if coupon is None:
                    return Response(
                        {"error": "Coupon not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if not coupon.is_active:
                    return Response(
                        {"error": "Coupon is inactive."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if coupon.redeemed_by_id is not None:
                    return Response(
                        {"error": "Coupon has already been redeemed."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if coupon.expires_at and coupon.expires_at < now:
                    return Response(
                        {"error": "Coupon has expired."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                user.cash = F('cash') + coupon.cash_amount
                user.save(update_fields=['cash'])
                user.refresh_from_db()

                coupon.redeemed_by = user
                coupon.redeemed_at = now
                coupon.save(update_fields=['redeemed_by', 'redeemed_at'])

        except Exception as e:
            logger.exception(
                "Coupon redemption failed. user=%s code=%s error=%s",
                request.user.pk,
                code,
                e,
            )
            return Response(
                {"error": "Internal server error while redeeming coupon."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "message": "Coupon redeemed successfully.",
                "redeemed_cash": coupon.cash_amount,
                "remaining_cash": user.cash,
            },
            status=status.HTTP_200_OK,
        )


# ──────────────────────────────────────────────
# 강의 대여 API
# ──────────────────────────────────────────────
class RentLectureView(APIView):
    """
    URL: /cash/rentals/

    보유한 캐시를 소모하여 특정 VOD '강의(Lecture)'를 대여하는 API View입니다.

    POST 요청 시, 대여할 강의 ID를 전달받아 현재 사용자가 동일 강의에 대해 활성 대여 내역을 가지고 있는지 검사합니다.
    이후 보유 중인 캐시가 강의 가격 이상인지 검증하고, 트랜잭션 내에서 유저의 캐시 차감 및 강의 대여 이력 생성을 원자적으로 처리합니다.

    Request Body:
        lecture_id (int): 대여할 강의 ID.

    Returns:
        Response: {
            "message": "Lecture rented successfully.",
            "rental_id": int,
            "remaining_cash": int,
            "expiration_date": str (ISO datetime)
        } (HTTP 201 Created)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = LectureRentalSerializer(data=request.data)
        logger.debug("[BACKEND_DEBUG_CASH] RentLecture Attempt - data: %s", request.data)
        serializer.is_valid(raise_exception=True)
        lecture_id = serializer.validated_data['lecture_id']

        # Atomic block for concurrency control
        try:
            with transaction.atomic():
                from django.contrib.auth import get_user_model
                User = get_user_model()

                # Lock the user and lecture
                user = User.objects.select_for_update().get(pk=request.user.pk)
                
                try:
                    lecture = Lecture.objects.get(pk=lecture_id)
                except Lecture.DoesNotExist:
                    return Response({"error": "Lecture not found."}, status=status.HTTP_404_NOT_FOUND)

                # Check if user already has an active rental
                from config.apps.lecture.services import has_valid_rental
                if has_valid_rental(user, lecture):
                    return Response(
                        {"error": "You already have an active rental for this lecture."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Check if user has enough cash
                if user.cash < lecture.price:
                    return Response(
                        {"error": "Insufficient cash. Please recharge."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Deduct cash
                user.cash = F('cash') - lecture.price
                user.save(update_fields=['cash'])
                user.refresh_from_db()

                # Create rental history
                rental = LectureRentalHistory.objects.create(
                    lecture=lecture,
                    student=user,
                    purchased_cash=lecture.price,
                    remaining_cash=user.cash
                )

                logger.debug("[BACKEND_DEBUG_CASH] Rent SUCCESS - user: %s, lecture: %s, remaining: %d", user.pk, lecture_id, user.cash)
                return Response({
                    "message": "Lecture rented successfully.",
                    "rental_id": rental.id,
                    "remaining_cash": user.cash,
                    "expiration_date": rental.created_at + timedelta(days=lecture.rental_period)
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("Rental failed for user=%s lecture=%s error=%s", request.user.pk, lecture_id, e)
            return Response(
                {"error": "Internal server error while processing rental."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ──────────────────────────────────────────────
# 강의 대여 취소(환불) API
# ──────────────────────────────────────────────
class CancelLectureRentalView(APIView):
    """
    URL: /cash/rentals/<pk>/cancel/

    결제(대여) 후 7일 이내인 VOD 강의에 대해 '대여 취소 및 환불'을 진행하는 API View입니다.

    POST 요청 시, 지정한 대여 ID의 대여 상태가 취소되지 않았으며 구매한 지 7일 이내인지 검증합니다.
    조건을 충족하면 트랜잭션 하에서 대여 상태를 canceled로 변경하고, 결제에 사용된 캐시 금액을 유저에게 즉시 복구(환불)합니다.

    Path Parameters:
        pk (int): 취소할 대여 기록(LectureRentalHistory) ID.

    Returns:
        Response: {
            "message": "Rental canceled and cash refunded.",
            "refunded_cash": int,
            "remaining_cash": int
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        try:
            with transaction.atomic():
                from django.contrib.auth import get_user_model
                User = get_user_model()

                user = User.objects.select_for_update().get(pk=request.user.pk)
                
                try:
                    # Lock the rental record
                    rental = LectureRentalHistory.objects.select_for_update().get(pk=pk, student=user)
                except LectureRentalHistory.DoesNotExist:
                    return Response({"error": "Rental record not found."}, status=status.HTTP_404_NOT_FOUND)

                if rental.is_canceled:
                    return Response({"error": "This rental is already canceled."}, status=status.HTTP_400_BAD_REQUEST)

                # Check if it is within 7 days
                now = timezone.now()
                cancellation_deadline = rental.created_at + timedelta(days=7)
                if now > cancellation_deadline:
                    return Response(
                        {"error": "Rental cannot be canceled after 7 days."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Refund cash
                user.cash = F('cash') + rental.purchased_cash
                user.save(update_fields=['cash'])
                user.refresh_from_db()

                # Mark as canceled
                rental.is_canceled = True
                rental.save(update_fields=['is_canceled'])

                return Response({
                    "message": "Rental canceled and cash refunded.",
                    "refunded_cash": rental.purchased_cash,
                    "remaining_cash": user.cash
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Rental cancellation failed for user=%s rental=%s error=%s", request.user.pk, pk, e)
            return Response(
                {"error": "Internal server error while processing cancellation."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ──────────────────────────────────────────────
# 구매(캐시 충전) 환불 API
# ──────────────────────────────────────────────
class RefundPurchaseView(APIView):
    """
    URL: /cash/webhook/apple/

    Apple App Store Server Notifications 환불 알림용 웹훅(Webhook) API View입니다.

    POST 요청 시, Apple V2 알림의 signedPayload (JWT) 서명을 확인 및 검증하여 REFUND 이벤트를 처리합니다.
    환불 대상 트랜잭션을 식별하고, 해당 유저의 충전 캐시 금액만큼 계정 캐시에서 즉시 차감(회수)하며 최소 0원으로 보정합니다. 인증이 필요하지 않습니다.

    Request Body:
        signedPayload (str): Apple 서명된 JWT 데이터.

    Returns:
        Response: {
            "message": str,
            "deducted_cash": int (환불 적용 시),
            "remaining_cash": int (환불 적용 시)
        }
    """
    permission_classes = []
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        signed_payload = request.data.get('signedPayload')

        if not signed_payload:
            return Response({"error": "Missing signedPayload"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            import jwt
            import base64
            from cryptography.x509 import load_der_x509_certificate
            from cryptography.hazmat.backends import default_backend

            # 1. Main Payload Verification
            unverified_header = jwt.get_unverified_header(signed_payload)
            x5c = unverified_header.get('x5c')
            if not x5c or not isinstance(x5c, list):
                return Response({"error": "Missing x5c in header"}, status=status.HTTP_400_BAD_REQUEST)

            leaf_cert_der = base64.b64decode(x5c[0])
            cert = load_der_x509_certificate(leaf_cert_der, default_backend())
            public_key = cert.public_key()

            decoded_payload = jwt.decode(
                signed_payload, 
                key=public_key, 
                algorithms=["ES256"], 
                options={"verify_signature": True, "verify_aud": False}
            )
            notification_type = decoded_payload.get('notificationType')

            # 환불 관련 이벤트만 로직 실행 (그 외 이벤트는 Apple 측 재전송을 막기 위해 200 응답)
            if notification_type not in ["REFUND", "REFUND_DECLINED"]:
                logger.info("Apple Webhook ignored notificationType: %s", notification_type)
                return Response({"message": "Event ignored"}, status=status.HTTP_200_OK)

            data = decoded_payload.get('data', {})
            signed_transaction_info = data.get('signedTransactionInfo')

            if not signed_transaction_info:
                return Response({"error": "Missing signedTransactionInfo"}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Transaction Info Payload Verification
            tx_unverified_header = jwt.get_unverified_header(signed_transaction_info)
            tx_x5c = tx_unverified_header.get('x5c')
            if not tx_x5c or not isinstance(tx_x5c, list):
                return Response({"error": "Missing tx x5c in header"}, status=status.HTTP_400_BAD_REQUEST)

            tx_leaf_cert_der = base64.b64decode(tx_x5c[0])
            tx_cert = load_der_x509_certificate(tx_leaf_cert_der, default_backend())
            tx_public_key = tx_cert.public_key()

            transaction_payload = jwt.decode(
                signed_transaction_info, 
                key=tx_public_key, 
                algorithms=["ES256"], 
                options={"verify_signature": True, "verify_aud": False}
            )
            transaction_id = transaction_payload.get('transactionId')

            if not transaction_id:
                return Response({"error": "Missing transactionId"}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                try:
                    # pk=pk나 특정 user가 아닌 애플에서 주는 transaction_id로 조회
                    purchase = PurchaseHistory.objects.select_for_update().get(transaction_id=transaction_id)
                except PurchaseHistory.DoesNotExist:
                    logger.warning("Refund Webhook: Purchase not found for tx_id=%s", transaction_id)
                    # 구매내역이 없어도 성공 처리(200)하여 재시도를 중단시키는 정책을 흔히 씁니다.
                    return Response({"message": "Purchase not found, ignoring."}, status=status.HTTP_200_OK)

                if notification_type == "REFUND_DECLINED":
                    logger.info("Apple Webhook: REFUND_DECLINED for tx_id=%s", transaction_id)
                    return Response({"message": "Refund Declined noted"}, status=status.HTTP_200_OK)

                if purchase.is_refunded:
                    logger.info("Apple Webhook: Already refunded tx_id=%s", transaction_id)
                    return Response({"message": "Already refunded"}, status=status.HTTP_200_OK)

                from django.contrib.auth import get_user_model
                User = get_user_model()
                # 구매내역 상의 유저를 조회 (요청자의 user 객체가 아님)
                user = User.objects.select_for_update().get(pk=purchase.user.pk)

                # 이미 쓴 캐시더라도 무조건 회수 (음수 방지용으로 0 보정)
                deducted = purchase.purchased_cash
                if user.cash < deducted:
                    logger.warning("User %s cash will be negative due to Apple Refund. Clamping to 0.", user.pk)
                    user.cash = 0
                    # 여기서 어뷰징 유저 계정을 블록하는 로직이 추가될 수 있습니다.
                else:
                    user.cash -= deducted

                user.save(update_fields=['cash'])
                user.refresh_from_db()

                purchase.is_refunded = True
                purchase.save(update_fields=['is_refunded'])

                logger.info(
                    "Apple Webhook success. Refund user=%s tx_id=%s deducted=%d remain=%d",
                    user.pk, transaction_id, deducted, user.cash
                )

                return Response({
                    "message": "Webhook processed, refund applied",
                    "deducted_cash": deducted,
                    "remaining_cash": user.cash
                }, status=status.HTTP_200_OK)

        except jwt.DecodeError as e:
            logger.exception("Apple Webhook JWT decode error: %s", e)
            return Response({"error": "JWT Decode Error"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Refund webhook failed: %s", e)
            return Response(
                {"error": "Internal server error while processing webhook."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ──────────────────────────────────────────────
# Google Play Store 환불 / 취소 알림 웹훅 (Pub/Sub)
# ──────────────────────────────────────────────
class GooglePlayWebhookView(APIView):
    """
    URL: /cash/webhook/google/

    Google Play Store 환불 및 취소 알림용 웹훅(Webhook) API View입니다.

    POST 요청 시, Pub/Sub 메시지 데이터를 디코딩하고 CANCELED (취소/환불) 이벤트인 경우 AndroidPublisher API를 통해 orderId를 획득합니다.
    해당 orderId를 갖는 PurchaseHistory 구매 건을 찾아 충전되었던 캐시 금액을 회수(차감) 처리하고 최소 0원으로 보정합니다. 인증이 필요하지 않습니다.

    Request Body:
        message (dict): Google Pub/Sub 데이터 포맷.

    Returns:
        Response: {
            "message": str,
            "deducted_cash": int (환불 적용 시),
            "remaining_cash": int (환불 적용 시)
        }
    """
    permission_classes = []
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        message = request.data.get('message', {})
        data_base64 = message.get('data')

        if not data_base64:
            return Response({"error": "Missing message data"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            import base64
            import json
            
            # 1. Base64 Decode
            data_json_str = base64.b64decode(data_base64).decode('utf-8')
            data_payload = json.loads(data_json_str)
            
            # 테스트 알림인 경우 200 OK 응답
            if data_payload.get('testNotification'):
                logger.info("Google Webhook: Test Notification received.")
                return Response({"message": "Test notification acknowledged"}, status=status.HTTP_200_OK)

            one_time_product_notification = data_payload.get('oneTimeProductNotification')
            if not one_time_product_notification:
                # 구독 등 다른 알림은 처리하지 않음
                return Response({"message": "Not a one-time product notification, ignoring"}, status=status.HTTP_200_OK)

            notification_type = one_time_product_notification.get('notificationType')
            purchase_token = one_time_product_notification.get('purchaseToken')
            # sku (상품 ID)가 필요한 경우 추출: sku = one_time_product_notification.get('sku')
            
            # Google RTDN (v1.0 기준) OneTimeProductNotification Type:
            # 1: ONE_TIME_PRODUCT_PURCHASED (성공)
            # 2: ONE_TIME_PRODUCT_CANCELED (사용자 취소/환불)
            if notification_type != 2:
                logger.info("Google Webhook ignored notificationType: %s", notification_type)
                return Response({"message": "Event ignored"}, status=status.HTTP_200_OK)

            if not purchase_token:
                return Response({"error": "Missing purchaseToken"}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Google Play Developer API (androidpublisher API) 로 orderId 조회
            # PurchaseHistory 모델에는 Google의 orderId가 transaction_id로 저장되어 있음
            # Webhook 알림에는 purchaseToken만 오기 때문에 orderId 조회가 필요함.
            
            product_id = one_time_product_notification.get('sku')
            package_name = getattr(settings, 'ANDROID_PACKAGE_NAME', None)
            service_account_path = getattr(settings, 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON', None)
            
            # orderId를 초기화
            order_id = None
            if package_name and service_account_path and product_id:
                try:
                    from google.oauth2 import service_account
                    from googleapiclient.discovery import build
                    
                    credentials = service_account.Credentials.from_service_account_file(
                        service_account_path,
                        scopes=['https://www.googleapis.com/auth/androidpublisher'],
                    )
                    service = build('androidpublisher', 'v3', credentials=credentials, cache_discovery=False)
                    
                    result = service.purchases().products().get(
                        packageName=package_name,
                        productId=product_id,
                        token=purchase_token,
                    ).execute()
                    
                    order_id = result.get('orderId')
                except Exception as e:
                    logger.warning("Google Webhook: Failed to fetch orderId via API: %s", e)

            with transaction.atomic():
                try:
                    # purchaseToken 또는 조회된 orderId 로 구매 내역 탐색 시도
                    # Google 구매 시에는 Google API의 orderId를 transaction_id에 저장함
                    if order_id:
                        purchase = PurchaseHistory.objects.select_for_update().get(transaction_id=order_id, platform='google')
                    else:
                        # orderId 조회를 생략하고 예비 시도 (단, 토큰 정보가 DB에 저장되어 있지 않으면 불가능할 수 있음)
                        raise PurchaseHistory.DoesNotExist
                        
                except PurchaseHistory.DoesNotExist:
                    logger.warning("Refund Webhook: Google Purchase not found for token=%s order_id=%s", purchase_token, order_id)
                    # 구매내역이 없어도 성공 처리(200)하여 재시도를 중단시킴
                    return Response({"message": "Purchase not found, ignoring."}, status=status.HTTP_200_OK)

                if purchase.is_refunded:
                    logger.info("Google Webhook: Already refunded tx_id=%s", purchase.transaction_id)
                    return Response({"message": "Already refunded"}, status=status.HTTP_200_OK)

                from django.contrib.auth import get_user_model
                User = get_user_model()
                # 구매내역 상의 유저를 조회
                user = User.objects.select_for_update().get(pk=purchase.user.pk)

                # 이미 쓴 캐시더라도 무조건 회수 (음수 방지용으로 0 보정)
                deducted = purchase.purchased_cash
                if user.cash < deducted:
                    logger.warning("User %s cash will be negative due to Google Refund. Clamping to 0.", user.pk)
                    user.cash = 0
                else:
                    user.cash -= deducted

                user.save(update_fields=['cash'])
                user.refresh_from_db()

                purchase.is_refunded = True
                purchase.save(update_fields=['is_refunded'])

                logger.info(
                    "Google Webhook success. Refund user=%s tx_id=%s deducted=%d remain=%d",
                    user.pk, purchase.transaction_id, deducted, user.cash
                )

                return Response({
                    "message": "Google Webhook processed, refund applied",
                    "deducted_cash": deducted,
                    "remaining_cash": user.cash
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Google Refund webhook failed: %s", e)
            return Response(
                {"error": "Internal server error while processing Google webhook."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ──────────────────────────────────────────────
# 캐시 구매 내역 조회 API
# ──────────────────────────────────────────────
class PurchaseHistoryListView(APIView):
    """
    URL: /cash/purchase-history/

    본인의 인앱 결제를 통한 '캐시 충전 내역(PurchaseHistory)' 목록을 최신순으로 조회하는 API View입니다.

    GET 요청 시, 현재 로그인한 사용자 본인의 전체 충전 거래 일시, 충전 금액, 실제 지불액, 잔여액 및 환불 완료 여부 목록을 반환합니다.

    Returns:
        Response: List[dict] 데이터 (각 항목당 id, date, purchased_cash, paid_amount, remaining_cash, is_refunded 포함)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        histories = PurchaseHistory.objects.filter(
            user=request.user
        ).order_by('-created_at')

        data = [
            {
                "id": h.id,
                "date": h.created_at.isoformat(),
                "purchased_cash": h.purchased_cash,
                "paid_amount": h.paid_amount,
                "remaining_cash": h.remaining_cash,
                "is_refunded": h.is_refunded,
            }
            for h in histories
        ]
        return Response(data, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────
# 강의 대여 내역 조회 API
# ──────────────────────────────────────────────
class RentalHistoryListView(APIView):
    """
    URL: /cash/rental-history/

    본인이 대여한 'VOD 강의 결제 내역(LectureRentalHistory)' 목록을 최신순으로 조회하는 API View입니다.

    GET 요청 시, 본인이 대여한 전체 강의 ID, 강의명, 대여 일시, 가격 및 취소 가능 여부(결제 후 7일 이내 및 취소 미진행 상태) 목록을 반환합니다.

    Returns:
        Response: List[dict] 데이터 (각 항목당 id, date, lecture_id, lecture_title, purchased_cash, remaining_cash, is_canceled, is_cancelable 포함)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta
        from django.utils import timezone

        rentals = LectureRentalHistory.objects.filter(
            student=request.user
        ).select_related('lecture').order_by('-created_at')

        now = timezone.now()
        data = []
        for r in rentals:
            cancelable = (
                not r.is_canceled and
                (now - r.created_at) <= timedelta(days=7)
            )
            data.append({
                "id": r.id,
                "date": r.created_at.isoformat(),
                "lecture_id": r.lecture_id,
                "lecture_title": r.lecture.title,
                "purchased_cash": r.purchased_cash,
                "remaining_cash": r.remaining_cash,
                "is_canceled": r.is_canceled,
                "is_cancelable": cancelable,
            })
        return Response(data, status=status.HTTP_200_OK)

import logging
import json

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle

from datetime import timedelta
from django.utils import timezone

from .serializers import CashPurchaseSerializer, LectureRentalSerializer
from .models import PurchaseHistory, LectureRentalHistory
from config.apps.lecture.models import Lecture

logger = logging.getLogger(__name__)

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


# ──────────────────────────────────────────────
# 구매 전용 Rate Throttle (유저당 분당 10회)
# ──────────────────────────────────────────────
class PurchaseRateThrottle(UserRateThrottle):
    rate = '10/min'


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
    service_account_path = getattr(settings, 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON', None)
    package_name = getattr(settings, 'ANDROID_PACKAGE_NAME', None)

    if not service_account_path or not package_name:
        logger.error(
            "Google Play settings missing. "
            "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON=%s, ANDROID_PACKAGE_NAME=%s",
            service_account_path, package_name
        )
        return False, None, "Server configuration error."

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

    except FileNotFoundError:
        logger.exception("Google service account JSON file not found: %s", service_account_path)
        return False, None, "Server configuration error."
    except ImportError:
        logger.exception("google-api-python-client is not installed.")
        return False, None, "Server configuration error."
    except Exception as e:
        logger.exception("Google Play verification failed: %s", e)
        return False, None, "Failed to verify with Google Play."


# ──────────────────────────────────────────────
# 캐시 구매 API
# ──────────────────────────────────────────────
class PurchaseCashView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PurchaseRateThrottle]

    def post(self, request):
        """
        캐시 구매 API

        [URL]:
        POST /cash/purchase/

        [Request Body]
        - Apple 결제:
            {
                "platform": "apple",
                "product_id": "cash_5000",
                "receipt_data": "<App Store에서 받은 Base64 인코딩된 영수증 데이터>"
            }

        - Google 결제:
            {
                "platform": "google",
                "product_id": "cash_5000",
                "purchase_token": "<Google Play에서 받은 구매 토큰>"
            }

        [사용 가능한 product_id]
            cash_100    -> 100캐시  (100원)
            cash_500    -> 500캐시  (500원)
            cash_1000   -> 1000캐시 (1,000원)
            cash_5000   -> 5000캐시 (5,000원)
            cash_10000  -> 10000캐시 (10,000원)
            cash_50000  -> 50000캐시 (50,000원)

        [Response - 성공 200 OK]
            {
                "message": "Cash purchased successfully",
                "purchased_cash": 5000,
                "remaining_cash": 15000
            }

        [Response - 실패 400 Bad Request]
            - 유효하지 않은 product_id:
                {"error": "Invalid product_id"}

            - 플랫폼 검증 실패:
                {"error": "Apple verification failed: <사유>"}
                {"error": "Google verification failed: <사유>"}

            - 중복 영수증 (이미 처리된 결제):
                {"error": "This transaction has already been processed."}
        """
        serializer = CashPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
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

        logger.info(
            "Purchase success. user=%s platform=%s product=%s cash=%d remaining=%d tx=%s",
            user.pk, platform, product_id, purchased_cash, user.cash, transaction_id,
        )

        return Response({
            "message": "Cash purchased successfully",
            "purchased_cash": purchased_cash,
            "remaining_cash": user.cash,
        }, status=status.HTTP_200_OK)


# ──────────────────────────────────────────────
# 강의 대여 API
# ──────────────────────────────────────────────
class RentLectureView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        강의 대여 API

        [URL]
        POST /cash/rentals/

        [Request Body]
        {
            "lecture_id": 123
        }

        [Response - 성공 201 Created]
        {
            "message": "Lecture rented successfully.",
            "rental_id": 45,
            "remaining_cash": 8000,
            "expiration_date": "2026-03-19T15:18:56Z"
        }

        [Response - 실패 400 Bad Request]
        - 이미 대여 중인 강의:
            {"error": "You already have an active rental for this lecture."}
        - 캐시 부족:
            {"error": "Insufficient cash. Please recharge."}

        [Response - 실패 404 Not Found]
        - 강의를 찾을 수 없음:
            {"error": "Lecture not found."}
        """

        serializer = LectureRentalSerializer(data=request.data)
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
                now = timezone.now()
                # A rental is active if not canceled and created_at + rental_period >= now
                active_rentals = LectureRentalHistory.objects.filter(
                    lecture=lecture,
                    student=user,
                    is_canceled=False
                )
                
                has_active = False
                for rental in active_rentals:
                    expiration_date = rental.created_at + timedelta(days=lecture.rental_period)
                    if expiration_date >= now:
                        has_active = True
                        break
                
                if has_active:
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
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """
        강의 대여 취소(환불) API

        [URL]
        POST /cash/rentals/<int:pk>/cancel/

        [Request Body]
        (Empty)

        [Response - 성공 200 OK]
        {
            "message": "Rental canceled and cash refunded.",
            "refunded_cash": 2000,
            "remaining_cash": 10000
        }

        [Response - 실패 400 Bad Request]
        - 이미 취소된 대여:
            {"error": "This rental is already canceled."}
        - 7일 경과 (취소 불가):
            {"error": "Rental cannot be canceled after 7 days."}

        [Response - 실패 404 Not Found]
        - 대여 내역을 찾을 수 없음:
            {"error": "Rental record not found."}
        """

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
    permission_classes = []

    def post(self, request, *args, **kwargs):
        """
        Apple App Store Server Notifications 환불 웹훅 URL API
        
        Apple V2 Notification 의 signedPayload (JWS) 를 파싱하여
        REFUND 혹은 REFUND_DECLINED 서버 알림을 처리합니다.
        
        [URL]
        POST /cash/webhook/apple/

        [Request Body]
        {
            "signedPayload": "eyJhbG..."
        }
        
        [주의]
        * 웹훅은 Apple 서버에서 호출하므로 인증(IsAuthenticated)을 해제합니다.
        * pk 등 기존 URL 파라미터가 들어오더라도 무시(*args, **kwargs)합니다.
        * 이미 상품을 소비해 캐시가 부족하더라도 Apple은 사용자에게 환불을 진행하므로 캐시를 0 뷰로 보정 차감합니다.
        """
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
    permission_classes = []

    def post(self, request, *args, **kwargs):
        """
        Google Play Developer API Real-time Developer Notifications (RTDN)
        환불 및 상태 변경 알림 웹훅

        [URL]
        POST /cash/webhook/google/

        [Request Body]
        {
            "message": {
                "data": "eyJ2ZXJzaW9uIjoiMS4wIiwi..." (Base64 Encoded JSON),
                "messageId": "1234567890",
                "publishTime": "2026-03-09T10:10:10.123Z"
            },
            "subscription": "projects/myproject/subscriptions/mysubscription"
        }
        """
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

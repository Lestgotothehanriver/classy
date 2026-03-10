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

from .serializers import CashPurchaseSerializer
from .models import PurchaseHistory

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

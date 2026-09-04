import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from config.throttles import PurchaseRateThrottle

from datetime import timedelta
from django.utils import timezone

from .serializers import (
    CashPurchaseSerializer,
    LectureRentalSerializer,
    RedeemCouponSerializer,
)
from .models import PurchaseHistory, LectureRentalHistory, Account, Coupon
from .constants import GOOGLE_PRODUCT_CASH_MAP, PRODUCT_CASH_MAP
from .apple_iap import (
    AppleIAPConfigurationError,
    AppleIAPConflictError,
    AppleIAPTemporaryError,
    AppleIAPVerificationError,
    grant_apple_purchase,
    process_apple_notification,
    verify_apple_transaction,
)
from .google_iap import (
    GoogleIAPConfigurationError,
    GoogleIAPConflictError,
    GoogleIAPTemporaryError,
    GoogleIAPVerificationError,
    process_google_notification,
    process_google_purchase,
)
from config.apps.lecture.models import Lecture

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 상품 매핑 (Store product_id → 캐시 / 원화)
# 가격 정책: 100캐시 = 120원 (캐시 × 1.2)
# ⚠️ krw는 서버가 기록/표시하는 값이며, 실제 청구액은 App Store / Play
#    콘솔의 상품 가격이 소스입니다. 스토어 상품 가격도 동일하게 맞춰야 합니다.
# ──────────────────────────────────────────────
class CashPackageListView(APIView):
    """캐시 충전 상품(패키지) 목록을 반환합니다.

    앱이 가격표를 하드코딩하지 않고 서버에서 내려받도록 하기 위한 조회 API입니다.
    price는 표시용 원화 금액이며, 실제 청구액은 스토어 상품 가격이 소스입니다.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.query_params.get('platform') == 'google':
            packages = [
                {
                    "productId": product_id,
                    "cash": info["cash"],
                    "price": info["krw"],
                    "platform": "google",
                    "obfuscatedAccountId": str(
                        request.user.google_play_account_token
                    ),
                }
                for product_id, info in GOOGLE_PRODUCT_CASH_MAP.items()
            ]
            return Response({"results": packages})

        packages = [
            {
                "productId": product_id,
                "cash": info["cash"],
                "price": info["krw"],
                "platform": "apple",
                "appAccountToken": str(request.user.apple_app_account_token),
            }
            for product_id, info in PRODUCT_CASH_MAP.items()
        ]
        return Response({"results": packages})


# PurchaseRateThrottle is imported from config.throttles


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
    """Verify one Apple or Google transaction and grant cash once."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [PurchaseRateThrottle]

    def post(self, request):
        serializer = CashPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        platform = serializer.validated_data['platform']
        product_id = serializer.validated_data['product_id']
        product_map = (
            GOOGLE_PRODUCT_CASH_MAP if platform == 'google' else PRODUCT_CASH_MAP
        )
        if product_id not in product_map:
            return Response(
                {"error": "Invalid product_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if platform == 'google':
            return self._purchase_google(
                request,
                product_id=product_id,
                purchase_token=serializer.validated_data['purchase_token'],
            )

        try:
            verified = verify_apple_transaction(
                serializer.validated_data['signed_transaction_info'],
                expected_product_id=product_id,
                expected_app_account_token=request.user.apple_app_account_token,
            )
            grant = grant_apple_purchase(request.user, verified)
        except AppleIAPVerificationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AppleIAPConflictError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except (AppleIAPConfigurationError, AppleIAPTemporaryError) as exc:
            logger.error('Apple IAP temporarily unavailable: %s', exc)
            return Response(
                {"error": "Apple purchase verification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception('Unexpected Apple purchase processing failure user=%s', request.user.pk)
            return Response(
                {"error": "Internal server error while processing Apple purchase."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        from django.contrib.auth import get_user_model
        current_user = get_user_model().objects.only('cash', 'cash_debt').get(
            pk=request.user.pk
        )

        return Response({
            "message": "Cash purchase processed successfully.",
            "purchase_id": grant.purchase.pk,
            "purchased_cash": grant.purchase.purchased_cash,
            "credited_cash": grant.credited_cash,
            "debt_offset": grant.debt_offset,
            "remaining_cash": current_user.cash,
            "cash_debt": current_user.cash_debt,
            "idempotent": grant.idempotent,
        }, status=status.HTTP_200_OK)

    def _purchase_google(self, request, *, product_id, purchase_token):
        """Process a Google purchase while keeping Apple handling isolated."""

        try:
            grant = process_google_purchase(request.user, product_id, purchase_token)
        except GoogleIAPVerificationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except GoogleIAPConflictError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except (GoogleIAPConfigurationError, GoogleIAPTemporaryError) as exc:
            logger.error(
                'Google Play purchase temporarily unavailable user=%s: %s',
                request.user.pk,
                exc,
            )
            return Response(
                {"error": "Google Play purchase verification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception(
                'Unexpected Google Play purchase processing failure user=%s',
                request.user.pk,
            )
            return Response(
                {"error": "Internal server error while processing Google Play purchase."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        current_user = get_user_model().objects.only('cash', 'cash_debt').get(
            pk=request.user.pk
        )
        return Response({
            "message": "Cash purchase processed successfully.",
            "purchase_id": grant.purchase.pk,
            "purchased_cash": grant.purchase.purchased_cash,
            "credited_cash": grant.credited_cash,
            "debt_offset": grant.debt_offset,
            "remaining_cash": current_user.cash,
            "cash_debt": current_user.cash_debt,
            "idempotent": grant.idempotent,
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

                # 판매 중지(is_active=False)/삭제(is_delete=True) 강의는 신규 대여 불가.
                # (탐색 목록에서 걸러지지만 stale 목록/딥링크로 도달할 수 있으므로 서버에서 최종 차단)
                if not lecture.is_active or lecture.is_delete:
                    return Response(
                        {"error": "판매 중지된 강의입니다."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 본인 강의는 대여할 수 없다. (강사 본인은 대여 없이 재생 가능하며,
                # 자기 강의를 대여해 매출/정산 데이터를 만드는 것을 서버에서 차단한다.)
                if lecture.instructor.user_id == user.pk:
                    return Response(
                        {"error": "본인 강의는 대여할 수 없습니다."},
                        status=status.HTTP_403_FORBIDDEN
                    )

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
                    "expiration_date": rental.expiration_date
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
        # 정책: 강의 대여는 완료 후 취소/캐시 환급이 불가능하다.
        # (환불 로직은 제거하며, is_canceled 필드는 관리자/스토어 강제 환불 등
        #  후속 파트의 예외 처리 호환을 위해 모델에는 유지한다.)
        logger.info(
            "[CASH] 대여 취소 시도 차단(정책상 불가). user_id=%s, rental_id=%s",
            request.user.pk, pk
        )
        return Response(
            {"error": "강의 대여는 취소할 수 없습니다."},
            status=status.HTTP_410_GONE,
        )


# ──────────────────────────────────────────────
# 구매(캐시 충전) 환불 API
# ──────────────────────────────────────────────
class RefundPurchaseView(APIView):
    """Verify and process App Store Server Notifications V2."""
    permission_classes = []
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        signed_payload = request.data.get('signedPayload')
        if not signed_payload:
            return Response(
                {"error": "Missing signedPayload"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = process_apple_notification(signed_payload)
        except AppleIAPVerificationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AppleIAPConflictError as exc:
            logger.error('Conflicting App Store notification: %s', exc)
            return Response(
                {"error": "Conflicting App Store notification."},
                status=status.HTTP_409_CONFLICT,
            )
        except (AppleIAPConfigurationError, AppleIAPTemporaryError) as exc:
            logger.error('App Store notification temporarily unavailable: %s', exc)
            return Response(
                {"error": "App Store notification verification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception('Unexpected App Store notification failure')
            return Response(
                {"error": "Internal server error while processing webhook."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "message": "App Store notification processed.",
                "duplicate": result.duplicate,
                "status": result.event.status,
            },
            status=status.HTTP_200_OK,
        )


class GooglePlayWebhookView(APIView):
    """Authenticate and process Google Play RTDN Pub/Sub push messages."""

    authentication_classes = []
    permission_classes = []
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        try:
            result = process_google_notification(
                request.data,
                authorization=request.headers.get('Authorization', ''),
            )
        except GoogleIAPVerificationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except GoogleIAPConflictError as exc:
            logger.error('Conflicting Google Play notification: %s', exc)
            return Response(
                {"error": "Conflicting Google Play notification."},
                status=status.HTTP_409_CONFLICT,
            )
        except (GoogleIAPConfigurationError, GoogleIAPTemporaryError) as exc:
            logger.error('Google Play notification temporarily unavailable: %s', exc)
            return Response(
                {"error": "Google Play notification is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception('Unexpected Google Play notification failure')
            return Response(
                {"error": "Internal server error while processing webhook."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "message": "Google Play notification processed.",
            "duplicate": result.duplicate,
            "status": result.event.status,
        }, status=status.HTTP_200_OK)


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
        rentals = LectureRentalHistory.objects.filter(
            student=request.user
        ).select_related('lecture').order_by('-created_at')

        data = []
        for r in rentals:
            # 정책상 대여 취소가 불가하므로 항상 False. (하위 호환을 위해 필드는 유지)
            cancelable = False
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

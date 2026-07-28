"""정산(Settlement) 관리 직렬화기입니다.

학력 인증(instructor_verification) 직렬화기와 동일한 패턴을 따릅니다. 목록은 최소
정보 + 수수료/지급 기준액 계산값을, 상세는 계좌 정보(전체)와 연결 대여 내역을
포함합니다. 계좌번호는 실제 송금을 위해 마스킹하지 않으며, 접근은 뷰의
``IsSuperAdmin`` 으로 제한됩니다.
"""

from rest_framework import serializers

from config.apps.cash.constants import PLATFORM_FEE_RATE
from config.apps.cash.models import Account, LectureRentalHistory, SettlementRecord

from .instructor_verification import _real_name


def _platform_fee(amount: int) -> int:
    return int(amount * PLATFORM_FEE_RATE)


class SettlementRentalSerializer(serializers.Serializer):
    """정산에 연결된 강의 대여(수익원) 한 건입니다."""

    id = serializers.IntegerField()
    lecture_title = serializers.SerializerMethodField()
    student = serializers.SerializerMethodField()
    purchased_cash = serializers.IntegerField()
    is_canceled = serializers.BooleanField()
    created_at = serializers.DateTimeField()

    def get_lecture_title(self, obj: LectureRentalHistory) -> str:
        return getattr(obj.lecture, "title", "")

    def get_student(self, obj: LectureRentalHistory) -> str:
        user = obj.student
        return _real_name(user)


class SettlementListSerializer(serializers.ModelSerializer):
    """정산 목록 항목입니다."""

    real_name = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    platform_fee = serializers.SerializerMethodField()
    payout_amount = serializers.SerializerMethodField()
    rental_count = serializers.SerializerMethodField()

    class Meta:
        model = SettlementRecord
        fields = [
            "id",
            "status",
            "amount",
            "platform_fee",
            "payout_amount",
            "real_name",
            "user_name",
            "created_at",
            "processed_at",
            "rental_count",
        ]

    def _user(self, obj: SettlementRecord):
        return obj.instructor.user

    def get_real_name(self, obj: SettlementRecord) -> str:
        return _real_name(self._user(obj))

    def get_user_name(self, obj: SettlementRecord) -> str:
        return self._user(obj).user_name

    def get_platform_fee(self, obj: SettlementRecord) -> int:
        return _platform_fee(obj.amount)

    def get_payout_amount(self, obj: SettlementRecord) -> int:
        return obj.amount - _platform_fee(obj.amount)

    def get_rental_count(self, obj: SettlementRecord) -> int:
        annotated = getattr(obj, "rental_count", None)
        return annotated if annotated is not None else obj.rentals.count()


class SettlementDetailSerializer(SettlementListSerializer):
    """상세 화면용. 강사 이메일·계좌 정보(전체)·연결 대여 내역을 포함합니다."""

    email = serializers.SerializerMethodField()
    account_info = serializers.SerializerMethodField()
    rentals = serializers.SerializerMethodField()

    class Meta(SettlementListSerializer.Meta):
        fields = SettlementListSerializer.Meta.fields + [
            "email",
            "account_info",
            "payment_reference",
            "admin_note",
            "rentals",
        ]

    def get_email(self, obj: SettlementRecord) -> str:
        return self._user(obj).email

    def get_account_info(self, obj: SettlementRecord):
        """강사 정산 계좌 정보(전체). 실제 송금용이라 마스킹하지 않습니다."""
        try:
            account = obj.instructor.account
        except Account.DoesNotExist:
            return None
        return {
            "bank": account.bank,
            "account_number": account.account_number,
            "account_holder": account.account_holder,
        }

    def get_rentals(self, obj: SettlementRecord):
        rentals = obj.rentals.select_related("lecture", "student").order_by("-created_at")
        return SettlementRentalSerializer(rentals, many=True).data


class SettlementCompleteSerializer(serializers.Serializer):
    """정산 완료 입력. 지급 참조번호는 필수입니다."""

    payment_reference = serializers.CharField()
    admin_note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_payment_reference(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("지급 참조번호를 입력해야 합니다.")
        return value


class SettlementCancelSerializer(serializers.Serializer):
    """정산 취소 입력. 사유는 선택(감사 로그 기록용)입니다."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")

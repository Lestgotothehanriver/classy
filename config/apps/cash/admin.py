from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from .models import (
    PurchaseHistory,
    LectureRentalHistory,
    InstructorMonthlyRank,
    Account,
    SettlementRecord,
    Coupon,
)

# 플랫폼 수수료율(정산 지급 기준 계산용 표시값). 실제 송금은 자동화하지 않는다.
PLATFORM_FEE_RATE = 0.20

@admin.register(PurchaseHistory)
class PurchaseHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'transaction_id', 'purchased_cash', 'paid_amount', 'fee_deducted_amount', 'remaining_cash', 'created_at', 'is_refunded')
    list_filter = ('platform', 'is_refunded', 'created_at')
    search_fields = ('user__username', 'transaction_id')
    readonly_fields = ('created_at',)

@admin.register(LectureRentalHistory)
class LectureRentalHistoryAdmin(admin.ModelAdmin):
    list_display = ('student', 'lecture', 'purchased_cash', 'remaining_cash', 'is_canceled', 'is_settled', 'created_at')
    list_filter = ('is_canceled', 'is_settled', 'created_at')
    search_fields = ('student__username', 'lecture__title')
    readonly_fields = ('created_at',)

@admin.register(InstructorMonthlyRank)
class InstructorMonthlyRankAdmin(admin.ModelAdmin):
    list_display = ('year', 'month', 'instructor', 'total_cash', 'rank', 'created_at')
    list_filter = ('year', 'month')
    search_fields = ('instructor__user__username',)
    readonly_fields = ('created_at',)

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('instructor', 'bank', 'account_number', 'account_holder')
    search_fields = ('instructor__user__username', 'bank', 'account_number', 'account_holder')

@admin.register(SettlementRecord)
class SettlementRecordAdmin(admin.ModelAdmin):
    list_display = (
        'instructor', 'amount', 'platform_fee_display', 'payout_base_display',
        'status', 'created_at', 'processed_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('instructor__user__username',)
    readonly_fields = (
        'created_at', 'processed_at',
        'total_cash_display', 'platform_fee_display', 'payout_base_display',
    )

    @admin.display(description='총 캐시')
    def total_cash_display(self, obj):
        return obj.amount

    @admin.display(description=f'플랫폼 수수료({int(PLATFORM_FEE_RATE * 100)}%)')
    def platform_fee_display(self, obj):
        return int(obj.amount * PLATFORM_FEE_RATE)

    @admin.display(description='지급 기준 캐시')
    def payout_base_display(self, obj):
        return obj.amount - int(obj.amount * PLATFORM_FEE_RATE)

    def save_model(self, request, obj, form, change):
        """
        상태 전이 처리:
        - PENDING -> COMPLETED: processed_at 기록(연결 대여는 유지).
        - PENDING/COMPLETED -> CANCELED: processed_at 기록 후, 연결된 대여를
          is_settled=False, settlement=None으로 롤백해 강사가 재신청할 수 있게 한다.
        실제 KRW 송금/계좌 처리는 이 화면에서 자동화하지 않는다.
        """
        old_status = None
        if change and obj.pk:
            old_status = (
                SettlementRecord.objects.filter(pk=obj.pk)
                .values_list('status', flat=True)
                .first()
            )

        with transaction.atomic():
            if old_status != obj.status and obj.status in ('COMPLETED', 'CANCELED'):
                obj.processed_at = timezone.now()

            super().save_model(request, obj, form, change)

            if old_status != 'CANCELED' and obj.status == 'CANCELED':
                obj.rentals.all().update(is_settled=False, settlement=None)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'cash_amount',
        'is_active',
        'expires_at',
        'redeemed_by',
        'redeemed_at',
        'created_at',
    )
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('code', 'redeemed_by__username', 'redeemed_by__user_name')
    readonly_fields = ('redeemed_at', 'created_at')

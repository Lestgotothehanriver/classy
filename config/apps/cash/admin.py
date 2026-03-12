from django.contrib import admin
from .models import PurchaseHistory, LectureRentalHistory, InstructorMonthlyRank, Account, SettlementRecord

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
    list_display = ('instructor', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('instructor__user__username',)
    readonly_fields = ('created_at',)

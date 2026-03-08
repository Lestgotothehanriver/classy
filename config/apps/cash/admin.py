from django.contrib import admin
from .models import PurchaseHistory

@admin.register(PurchaseHistory)
class PurchaseHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'purchased_cash', 'paid_amount', 'created_at')
    list_filter = ('platform', 'created_at')
    search_fields = ('user__username', 'transaction_id')

from django.db import models

from django.conf import settings

class PurchaseHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchases')
    platform = models.CharField(max_length=20, choices=[('apple', 'Apple'), ('google', 'Google')])
    transaction_id = models.CharField(max_length=255, unique=True, help_text="결제 플랫폼 고유 트랜잭션 ID")
    
    # Amount of cash purchased (e.g., 1000)
    purchased_cash = models.PositiveIntegerField()
    # Actual amount paid by the user in KRW
    paid_amount = models.PositiveIntegerField()
    # Amount after deducting 30% store fee
    fee_deducted_amount = models.PositiveIntegerField()
    # Cash balance remaining after this purchase
    remaining_cash = models.PositiveIntegerField()
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.platform} - {self.purchased_cash} cash"

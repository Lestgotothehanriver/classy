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
    is_refunded = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user} - {self.platform} - {self.purchased_cash} cash"

class LectureRentalHistory(models.Model):
    lecture = models.ForeignKey('lecture.Lecture', on_delete=models.CASCADE, related_name='rentals')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lecture_rentals')
    purchased_cash = models.PositiveIntegerField()
    remaining_cash = models.PositiveIntegerField()
    is_canceled = models.BooleanField(default=False)
    is_settled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} rented {self.lecture} for {self.purchased_cash} cash"

class InstructorMonthlyRank(models.Model):
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    instructor = models.ForeignKey('accounts.Instructor', on_delete=models.CASCADE, related_name='monthly_ranks')
    total_cash = models.PositiveIntegerField(default=0)
    rank = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('year', 'month', 'instructor')
        ordering = ['-year', '-month', 'rank']

    def __str__(self):
        return f"{self.year}-{self.month} Rank {self.rank}: {self.instructor.user.user_name} ({self.total_cash} cash)"

class Account(models.Model):
    instructor = models.OneToOneField('accounts.Instructor', on_delete=models.CASCADE, related_name='account')
    bank = models.CharField(max_length=100)
    account_number = models.CharField(max_length=100)
    account_holder = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.instructor.user.user_name} - {self.bank} {self.account_number}"

class SettlementRecord(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '대기'),
        ('COMPLETED', '정산완료'),
    ]
    instructor = models.ForeignKey('accounts.Instructor', on_delete=models.CASCADE, related_name='settlements')
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Settlement: {self.instructor.user.user_name} - {self.amount} ({self.get_status_display()})"

from django.db import models

from django.conf import settings

# ════════════════════════════════════════════════════════════════════════════════
# 금융 및 정산 관련 모델
# ════════════════════════════════════════════════════════════════════════════════

class PurchaseHistory(models.Model):
    """
    사용자의 인앱 결제(캐시 충전) 내역을 관리하는 모델입니다.
    
    Apple In-App Purchase 또는 Google Play Billing을 통해 사용자가 지불한
    실제 원화(KRW) 금액과 수수료, 그리고 지급된 가상 재화(Cash) 정보를 기록합니다.

    Attributes:
        user (ForeignKey): 결제를 진행하여 캐시를 충전한 사용자.
        platform (str): 결제를 수행한 플랫폼 (apple 또는 google).
        transaction_id (str): 결제 플랫폼에서 발급한 고유 결제 영수증 번호.
        purchased_cash (int): 사용자 지갑에 실제 충전된 캐시(가상 재화) 양.
        paid_amount (int): 사용자가 결제한 실제 금액 (예: 11,000원).
        fee_deducted_amount (int): 플랫폼 수수료(약 30%)를 제외하고 회사로 입금될 예정 금액.
        remaining_cash (int): 결제 성공 직후 시점의 사용자 보유 잔여 캐시.
        created_at (DateTimeField): 결제 완료 일시.
        is_refunded (bool): 해당 결제건에 대한 환불 처리 완료 여부.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchases')
    platform = models.CharField(max_length=20, choices=[('apple', 'Apple'), ('google', 'Google')])
    transaction_id = models.CharField(max_length=255, unique=True, help_text="결제 플랫폼 고유 트랜잭션 ID")
    
    purchased_cash = models.PositiveIntegerField()
    paid_amount = models.PositiveIntegerField()
    fee_deducted_amount = models.PositiveIntegerField()
    remaining_cash = models.PositiveIntegerField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    is_refunded = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user} - {self.platform} - {self.purchased_cash} cash"


class Coupon(models.Model):
    """
    이벤트 및 프로모션 목적으로 발행되는 '캐시 교환 쿠폰' 모델입니다.
    
    사용자가 특정 쿠폰 번호(code)를 입력하면 설정된 금액(cash_amount)만큼
    지갑(Cash)이 충전되며, 한 쿠폰당 한 번만 사용 가능하도록 처리됩니다.

    Attributes:
        code (str): 중복되지 않는 고유 쿠폰 번호 (영문/숫자 혼합 등).
        cash_amount (int): 쿠폰 사용 시 지급될 캐시 금액.
        is_active (bool): 쿠폰의 현재 사용 가능 여부 (관리자가 수동으로 비활성화 가능).
        expires_at (DateTimeField): 쿠폰 유효기간 만료 일시.
        redeemed_by (ForeignKey): 쿠폰을 사용하여 혜택을 받은 사용자.
        redeemed_at (DateTimeField): 쿠폰을 실제 사용(교환)한 일시.
        created_at (DateTimeField): 쿠폰 생성 일시.
    """
    code = models.CharField(max_length=50, unique=True, db_index=True)
    cash_amount = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='redeemed_coupons',
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.cash_amount} cash)"

class LectureRentalHistory(models.Model):
    """
    학생이 보유한 캐시를 소모하여 특정 '강의(VOD)'를 대여(결제)한 내역 모델입니다.
    
    강의 열람 권한 확인 및 강사에게 수익금을 분배(정산)하기 위한 
    핵심 원장(Ledger) 데이터로 사용됩니다.

    Attributes:
        lecture (ForeignKey): 학생이 결제(대여)한 대상 강의.
        student (ForeignKey): 결제를 진행한 학생.
        purchased_cash (int): 대여를 위해 소모한 캐시 비용.
        remaining_cash (int): 대여 결제 직후 시점의 학생 잔여 캐시.
        is_canceled (bool): 환불 또는 취소되어 대여가 무효화되었는지 여부.
        is_settled (bool): 강사에게 해당 대여건에 대한 수익 정산이 완료되었는지 여부.
        created_at (DateTimeField): 강의 대여(결제) 일시.
    """
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
    """
    월별로 강사들이 벌어들인 누적 수익 캐시를 집계하고 순위를 매기는 모델입니다.
    
    플랫폼 메인 화면의 '이달의 탑 강사' 노출 및 강사들의 월간 성과 리포팅 등에
    사용하기 위해 데이터를 정규화하여 저장합니다.

    Attributes:
        year (int): 랭킹 대상 연도 (예: 2026).
        month (int): 랭킹 대상 월 (예: 4).
        instructor (ForeignKey): 랭킹에 등재된 강사.
        total_cash (int): 해당 연/월에 발생한 강의 대여료의 총합(캐시 단위).
        rank (int): 해당 연/월의 수익 랭킹(순위).
        created_at (DateTimeField): 랭킹 데이터가 계산/저장된 일시.
    """
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
    """
    강사가 수익금을 실제 현금으로 출금받기 위한 정산용 은행 계좌 정보 모델입니다.
    
    실명 확인 및 입금 처리에 사용되며 강사별로 하나의 주 계좌만 등록할 수 있습니다.

    Attributes:
        instructor (OneToOneField): 계좌를 소유한 강사.
        bank (str): 은행명 (예: 신한은행, 카카오뱅크 등).
        account_number (str): 하이픈(-)이 포함되거나 없는 숫자 형태의 계좌 번호.
        account_holder (str): 통장 예금주 (신원 검증용).
    """
    instructor = models.OneToOneField('accounts.Instructor', on_delete=models.CASCADE, related_name='account')
    bank = models.CharField(max_length=100)
    account_number = models.CharField(max_length=100)
    account_holder = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.instructor.user.user_name} - {self.bank} {self.account_number}"

class SettlementRecord(models.Model):
    """
    강사가 자신의 누적 수익(캐시)을 현금으로 출금 요청한 '정산 신청 내역' 모델입니다.
    
    관리자가 내역을 확인 후 실제 은행 송금을 완료하면 상태(status)가 PENDING에서
    COMPLETED로 변경되며, 이후 강사에게 알림이 발송됩니다.

    Attributes:
        instructor (ForeignKey): 정산(출금)을 요청한 강사.
        amount (int): 정산 요청한 금액(캐시). (실제 입금 시 플랫폼 수수료 정책이 적용됨)
        status (str): 정산 처리 상태 (PENDING: 관리자 확인 대기, COMPLETED: 송금 완료).
        created_at (DateTimeField): 출금 요청 일시.
    """
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

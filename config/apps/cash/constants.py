# 유료 강의 대여 정책 상수.
#
# 모든 유료 강의 대여는 30일 이용권으로 고정한다. (강사가 기간을 임의로 정할 수 없음)
# 대여 만료일 계산·검증에서 이 값을 단일 출처(SSOT)로 사용한다.
LECTURE_RENTAL_DAYS = 30

# App Store product identifier -> granted cash and fallback KRW display price.
# The signed Apple transaction is the source for the actual charged price. The
# fallback price exists for older history rows and server-side display only.
PRODUCT_CASH_MAP = {
    'cash_500': {'cash': 500, 'krw': 600},
    'cash_1000': {'cash': 1000, 'krw': 1200},
    'cash_5000': {'cash': 5000, 'krw': 6000},
    'cash_10000': {'cash': 10000, 'krw': 12000},
    'cash_50000': {'cash': 50000, 'krw': 60000},
}

# Accounting estimate only. App Store Connect financial reports remain the
# source of truth for actual proceeds.
STORE_FEE_RATE = 0.30

# 플랫폼 수수료율(정산 지급 기준 계산용 표시값). 실제 송금은 자동화하지 않는다.
# 정산 지급 기준액 = amount - int(amount * PLATFORM_FEE_RATE).
# Django Admin과 관리자 API(adminops) 정산 계산이 이 값을 단일 출처(SSOT)로 공유한다.
PLATFORM_FEE_RATE = 0.20

# 유료 강의 대여 정책 상수.
#
# 모든 유료 강의 대여는 30일 이용권으로 고정한다. (강사가 기간을 임의로 정할 수 없음)
# 대여 만료일 계산·검증에서 이 값을 단일 출처(SSOT)로 사용한다.
LECTURE_RENTAL_DAYS = 30

# 플랫폼 수수료율(정산 지급 기준 계산용 표시값). 실제 송금은 자동화하지 않는다.
# 정산 지급 기준액 = amount - int(amount * PLATFORM_FEE_RATE).
# Django Admin과 관리자 API(adminops) 정산 계산이 이 값을 단일 출처(SSOT)로 공유한다.
PLATFORM_FEE_RATE = 0.20

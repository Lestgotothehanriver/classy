import math
from datetime import timedelta
from django.utils import timezone
from config.apps.cash.models import LectureRentalHistory
from config.apps.cash.constants import LECTURE_RENTAL_DAYS

# 판매 중지 후 삭제까지의 최소 대기 기간(일).
DELETE_GRACE_DAYS = 30

def get_lecture_rental_status(user, lecture):
    """
    주어진 유저와 강의에 대한 현재 대여 상태를 반환합니다.
    
    Returns:
        str: 'valid' (유효한 대여 존재), 'expired' (유효기간 만료), 'none' (대여 기록 없음 또는 모두 취소됨)
    """
    rentals = LectureRentalHistory.objects.filter(
        lecture=lecture,
        student=user
    ).order_by('-created_at')

    if not rentals.exists():
        return "none"

    now = timezone.now()
    has_expired = False

    for rental in rentals:
        if not rental.is_canceled:
            # 대여 시점에 확정 저장된 만료일 사용 (레거시 null은 30일 정책으로 보정).
            expiration_date = rental.expiration_date or (
                rental.created_at + timedelta(days=LECTURE_RENTAL_DAYS)
            )
            if expiration_date >= now:
                return "valid"
            has_expired = True
            
    if has_expired:
        return "expired"
        
    return "none"

def has_valid_rental(user, lecture):
    """
    현재 유효한 강의 대여를 보유하고 있는지 여부를 반환합니다.
    """
    return get_lecture_rental_status(user, lecture) == "valid"


def can_comment_on_lecture(user, lecture):
    """
    강의 댓글 쓰기 권한 보유 여부를 반환합니다.

    무료/프리뷰 강의는 재생 권한과 동일하게 로그인 사용자에게 댓글 작성을
    허용합니다. 유료 강의는 강의 소유자 또는 유효 대여자만 댓글을 작성,
    수정, 삭제할 수 있습니다.
    """
    if not user or not user.is_authenticated:
        return False

    if lecture.price == 0 or lecture.is_preview:
        return True

    if lecture.instructor.user_id == user.id:
        return True

    return has_valid_rental(user, lecture)


def get_lecture_delete_eligibility(lecture):
    """
    판매 중지된 강의의 '하드(소프트) 삭제' 가능 여부를 판정합니다.

    정책 (이중 체크):
      1. 대여 이력이 아예 없으면 즉시 삭제 가능.
      2. 판매 중지 전환 시점(suspended_at) + DELETE_GRACE_DAYS(30일)이 지나지 않았으면 대기.
      3. 현재 대여중(만료되지 않은) 학생이 한 명이라도 있으면 삭제 불가.
      4. 위 조건을 모두 통과하면 삭제 가능.

    '대여중' 여부는 저장된 `expiration_date > now`로 판별한다.

    Returns:
        tuple[str, int]: (status, days_remaining)
            status: 'deletable' | 'grace_period' | 'active_renter'
            days_remaining: grace_period일 때 남은 일수(올림), 그 외 0.
    """
    now = timezone.now()
    rentals = LectureRentalHistory.objects.filter(lecture=lecture, is_canceled=False)

    # 1) 대여 이력이 전혀 없으면 즉시 삭제 가능
    if not rentals.exists():
        return ("deletable", 0)

    # 2) 판매 중지 후 30일 grace (suspended_at이 없는 레거시 레코드는 grace 통과)
    if lecture.suspended_at:
        grace_end = lecture.suspended_at + timedelta(days=DELETE_GRACE_DAYS)
        if now < grace_end:
            days_remaining = max(1, math.ceil((grace_end - now).total_seconds() / 86400))
            return ("grace_period", days_remaining)

    # 3) 현재 대여중(만료 전) 학생 존재 여부 — 저장된 만료일로 단일 쿼리 판정
    if rentals.filter(expiration_date__gt=now).exists():
        return ("active_renter", 0)

    # 4) 모두 통과 → 삭제 가능
    return ("deletable", 0)

from datetime import timedelta
from django.utils import timezone
from config.apps.cash.models import LectureRentalHistory

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
            expiration_date = rental.created_at + timedelta(days=lecture.rental_period)
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

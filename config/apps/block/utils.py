from .models import Block

def get_blocked_user_ids(user):
    """
    지정된 유저가 차단한 대상 유저들의 ID 리스트를 반환합니다.
    """
    if not user or not user.is_authenticated:
        return []
    return list(Block.objects.filter(user=user).values_list("blocked_user_id", flat=True))

from .models import Block
from django.db.models import Q


def get_blocked_user_ids(user):
    """
    현재 유저와 어느 방향으로든 차단 관계가 있는 상대 유저 ID를 반환합니다.
    """
    if not user or not user.is_authenticated:
        return []
    relations = Block.objects.filter(
        Q(user=user) | Q(blocked_user=user)
    ).values_list("user_id", "blocked_user_id")
    return list({
        blocked if blocker == user.pk else blocker
        for blocker, blocked in relations
    })


def users_have_block_relation(first_user, second_user):
    """두 사용자 사이에 어느 방향으로든 차단 관계가 있는지 반환합니다."""
    if not first_user or not second_user:
        return False
    return Block.objects.filter(
        Q(user=first_user, blocked_user=second_user)
        | Q(user=second_user, blocked_user=first_user)
    ).exists()

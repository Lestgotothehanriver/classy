from .models import ChatMessage


def mark_messages_read_through(*, room_id, message_id, user):
    """[message_id] 이하의 방 메시지를 [user]가 읽은 것으로 표시한다.

    대상 메시지가 해당 방에 없으면 ``None``을 반환하고, 성공하면 대상 메시지의
    현재 읽은 사용자 수를 반환한다.
    """
    messages = ChatMessage.objects.filter(
        room_id=room_id,
        pk__lte=message_id,
    )
    target = messages.filter(pk=message_id).first()
    if target is None:
        return None

    for message in messages.exclude(read_by=user):
        message.read_by.add(user)

    return target.read_by.count()

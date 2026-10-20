"""티켓 관계 검증·상태 전이·감사 이력을 한곳에서 처리합니다."""

from django.db import transaction
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from config.apps.cash.models import PurchaseHistory
from config.apps.pending.models import PendingInstructor
from config.apps.tutoring.models import TutoringRegistration

from .models import (
    SupportConversation,
    SupportConversationMessage,
    SupportEvent,
    SupportMessage,
    SupportTicket,
)


USER_EVENT_TYPES = ("ticket.created", "ticket.reopened")
STATUS_LABELS = {
    SupportTicket.Status.RECEIVED: "접수됨",
    SupportTicket.Status.IN_PROGRESS: "처리 중",
    SupportTicket.Status.WAITING_FOR_USER: "추가 정보 필요",
    SupportTicket.Status.RESOLVED: "처리 완료",
    SupportTicket.Status.CLOSED: "종결됨",
}
REFUND_STATUS_LABELS = {
    "not_requested": "환불 요청 없음",
    "manual_review": "운영 검토 필요",
    "refunded": "환불 완료",
}

KAKAO_CUSTOMER_CENTER_URL = "https://pf.kakao.com/_YxhWxlX"
KAKAO_CUSTOMER_CENTER_LABEL = "고객센터 바로가기"

# 회원이 실제 고객지원 대화 화면을 열고 있는지를 사용자 단위로 보관한다.
# 일반 채팅 Presence와 마찬가지로 한 기기라도 열려 있으면 해당 회원의 모든
# 기기에 채팅 FCM을 보내지 않는다.
SUPPORT_PRESENCE_KEY = "support:conversation:{conversation_id}:member_online"


def support_member_is_online(conversation_id: int, user_id: int) -> bool:
    """Return whether [user_id] currently has the support room open."""
    presence = cache.get(SUPPORT_PRESENCE_KEY.format(conversation_id=conversation_id)) or {}
    return bool(presence.get(str(user_id)))


def add_support_member_presence(
    conversation_id: int, user_id: int, channel_name: str
) -> None:
    """Record one [channel_name] viewing the member support room."""
    key = SUPPORT_PRESENCE_KEY.format(conversation_id=conversation_id)
    presence = cache.get(key) or {}
    user_channels = set(presence.get(str(user_id), []))
    user_channels.add(channel_name)
    presence[str(user_id)] = list(user_channels)
    cache.set(key, presence, timeout=60 * 60 * 24)


def remove_support_member_presence(
    conversation_id: int, user_id: int, channel_name: str
) -> None:
    """Remove one disconnected [channel_name] from member room Presence."""
    key = SUPPORT_PRESENCE_KEY.format(conversation_id=conversation_id)
    presence = cache.get(key) or {}
    user_key = str(user_id)
    user_channels = set(presence.get(user_key, []))
    user_channels.discard(channel_name)
    if user_channels:
        presence[user_key] = list(user_channels)
    else:
        presence.pop(user_key, None)
    cache.set(key, presence, timeout=60 * 60 * 24)

STUDENT_WELCOME_MESSAGE = """클래씨에 가입하신 것을 환영해요!🎉

클래씨에서는 필요한 강의만 골라 시청하고, 마음에 드는 선생님을 찾아 과외를 시작할 수 있어요.

[클래씨 이용 방법]

① 필요한 강의 찾아보기

원하는 과목, 원하는 부분의 강의만 찾아서 학습할 수 있어요.

② 나에게 맞는 선생님 찾기

선생님이 필요한가요? 과외 메뉴에서 나에게 딱 맞는 선생님을 직접 찾아보거나, 과외 요청서를 등록해 다양한 선생님들의 제안을 받아보세요.

③ 선생님과 대화하기

강의에 댓글을 남기거나, 과외 제안서를 보내면 선생님과 대화를 할 수 있어요. 궁금한 내용, 혹은 원하는 내용이 있다면 선생님과 상담을 진행해보세요.

필요한 강의, 원하는 과외. 모두 클래씨에서 만나보세요!

서비스 이용중 궁금한 점이나 불편한 점이 있다면 언제든 아래 카카오톡 고객센터로 문의해주세요."""

STUDENT_PAYBACK_MESSAGE = """[과외비 페이백 혜택]

원하는 선생님과 과외가 성사되셨나요?

선생님과의 채팅창 상단의 [성사 등록하고 페이백 받기] 버튼을 눌러주세요. 선생님과 회원님이 모두 성사 등록을 하시면 첫 달 과외비의 0.5%를 페이백 혜택으로 지급받으실 수 있어요!"""

INSTRUCTOR_WELCOME_MESSAGE = """클래씨의 선생님이 되신 것을 환영해요! 🎉

안녕하세요! 선생님의 새로운 시작을 함께할 교육 플랫폼 클래씨에요.

클래씨에서는 직접 과외 학생을 찾거나, 강의를 등록하고 판매하여 수익을 얻을 수 있어요.

[클래씨 이용 방법]

① 선생님 프로필 작성하기

담당 과목과 수업 방식, 자신만의 강점을 자세히 소개해 보세요. 구체적인 프로필은 학생과 학부모님에게 신뢰감을 줄 수 있어요.

② 강의 등록하고 판매하기

선생님의 수업을 강의로 등록해보세요. 과외를 시작하기 전 학생들이 선생님의 실제 수업 스타일을 미리 경험할 수 있고, 강의 판매 수익도 얻을 수 있어요. 또한 경력이 많지 않더라도 강의를 통해 자신만의 수업 역량을 보여줄 수 있어요! 유료로 업로드한 강의가 판매되었다면, [강의 관리 및 정산] 메뉴에서 수익 정산을 신청할 수 있어요. 

③ 과외 학생 찾기

학생들이 등록한 과외 요청서를 확인하고, 조건에 맞는 학생에게 과외 제안서를 보내보세요. 선생님의 프로필이나 강의를 보고 학생이 직접 과외를 요청할 수도 있어요.

④ 성사 등록 하기

과외가 성사되었다면 채팅창 상단의 [성사 등록] 버튼을 눌러 성사 등록을 완료하고 이용요금을 지불해 주세요.
납부해주신 이용요금이 선생님의 클래씨 랭킹에 반영되고, 클래씨 랭킹이 높을수록 선생님의 과외 제안서가 상단에 노출돼요.

선생님의 수업이 더 많은 학생에게 닿을 수 있도록, 클래씨가 함께할게요!

서비스 이용중 궁금한 점이나 불편한 점이 있다면 언제든 아래 카카오톡 고객센터로 문의해주세요."""


def status_label(status: str) -> str:
    """사용자·운영 화면에 표시할 티켓 상태명을 반환합니다."""
    return STATUS_LABELS.get(status, "접수됨")


def refund_status_label(status: str) -> str:
    """운영 화면에 표시할 구매 환불 상태명을 반환합니다."""
    return REFUND_STATUS_LABELS.get(status, "상태 확인 필요")


def display_name(user) -> str:
    """삭제 후에도 표시할 수 있는 현재 사용자 표시 이름을 반환합니다."""
    return f"{user.last_name}{user.first_name}".strip() or user.user_name or user.username


def ticket_role(user, requested_role: str = "") -> str:
    """요청자가 실제 보유한 역할만 티켓 알림 역할로 저장합니다."""
    roles = set()
    if hasattr(user, "student_profile"):
        roles.add("student")
    if hasattr(user, "instructor_profile"):
        roles.add("instructor")
    if requested_role in roles:
        return requested_role
    return "instructor" if roles == {"instructor"} else "student"


def validate_related_target(*, user, related_kind: str, related_id: int | None):
    """티켓 요청자가 연결 대상의 실제 소유자/당사자인지 검증합니다."""
    if not related_kind and related_id is None:
        return None
    if not related_kind or related_id is None:
        raise ValidationError("연결 업무 정보가 올바르지 않습니다.")
    if related_kind == SupportTicket.RelatedKind.PURCHASE:
        target = PurchaseHistory.objects.filter(pk=related_id, user=user).first()
    elif related_kind == SupportTicket.RelatedKind.TUTORING_REGISTRATION:
        target = TutoringRegistration.objects.filter(pk=related_id).filter(
            student=user
        ).first() or TutoringRegistration.objects.filter(pk=related_id, instructor=user).first()
    elif related_kind == SupportTicket.RelatedKind.INSTRUCTOR_VERIFICATION:
        target = PendingInstructor.objects.filter(pk=related_id, instructor_profile__user=user).first()
    else:
        raise ValidationError("지원하지 않는 연결 업무입니다.")
    if target is None:
        raise ValidationError("본인의 연결 업무만 문의에 추가할 수 있습니다.")
    return target


def related_summary(ticket: SupportTicket) -> dict | None:
    """원본 업무 상태를 티켓 제목이 아닌 검증된 식별자로 읽어 요약합니다."""
    if not ticket.related_id:
        return None
    if ticket.related_kind == SupportTicket.RelatedKind.PURCHASE:
        row = PurchaseHistory.objects.filter(pk=ticket.related_id).first()
        if row is None:
            return None
        google_order_id = ""
        if row.platform == "google":
            google_detail = getattr(row, "google_play_detail", None)
            google_order_id = getattr(google_detail, "order_id", "")
        return {
            "kind": ticket.related_kind,
            "id": row.pk,
            "label": row.product_id or row.transaction_id,
            "status": row.refund_status,
            "refund_status_label": refund_status_label(row.refund_status),
            "platform": row.platform,
            "transaction_id": row.transaction_id,
            "store_order_id": google_order_id or row.transaction_id,
            "original_transaction_id": row.original_transaction_id,
            "purchased_cash": row.purchased_cash,
            "paid_amount": row.paid_amount,
            "is_refunded": row.is_refunded,
        }
    if ticket.related_kind == SupportTicket.RelatedKind.TUTORING_REGISTRATION:
        row = TutoringRegistration.objects.filter(pk=ticket.related_id).first()
        return None if row is None else {"kind": ticket.related_kind, "id": row.pk, "label": row.subject, "status": row.contract_status}
    if ticket.related_kind == SupportTicket.RelatedKind.INSTRUCTOR_VERIFICATION:
        row = PendingInstructor.objects.filter(pk=ticket.related_id).first()
        return None if row is None else {"kind": ticket.related_kind, "id": row.pk, "label": row.instructor_profile.university or "학력 인증", "status": row.status}
    return None


def ticket_context(user) -> dict:
    """문의 유형별로 사용자가 선택할 수 있는 검증 대상만 반환합니다."""
    purchases = PurchaseHistory.objects.filter(user=user).order_by("-created_at", "-pk")[:100]
    registrations = (
        TutoringRegistration.objects.filter(student=user)
        | TutoringRegistration.objects.filter(instructor=user)
    ).order_by("-updated_at", "-pk")[:100]
    verifications = PendingInstructor.objects.filter(
        instructor_profile__user=user
    ).order_by("-applied_at", "-pk")[:20]
    return {
        "purchases": [
            {
                "id": purchase.pk,
                "label": f"{purchase.purchased_cash:,} 캐시 충전",
                "created_at": purchase.created_at,
            }
            for purchase in purchases
        ],
        "tutoring_registrations": [
            {
                "id": registration.pk,
                "label": registration.subject,
                "updated_at": registration.updated_at,
                "status": registration.get_contract_status_display(),
            }
            for registration in registrations
        ],
        "instructor_verifications": [
            {
                "id": verification.pk,
                "label": verification.instructor_profile.university or "학력 인증 신청",
                "applied_at": verification.applied_at,
                "status": verification.get_status_display(),
            }
            for verification in verifications
        ],
    }


def add_event(ticket, *, actor, event_type: str, payload: dict | None = None) -> None:
    """변경 이력을 보존합니다."""
    SupportEvent.objects.create(
        ticket=ticket,
        actor=actor,
        actor_name=display_name(actor) if actor else "",
        event_type=event_type,
        payload=payload or {},
    )


def mark_ticket_read(ticket: SupportTicket, *, user) -> SupportTicket:
    """요청자가 확인한 시각을 기록해 운영자 답변 읽음 여부를 갱신합니다."""
    if ticket.requester_id != user.id:
        raise ValidationError("본인의 문의만 확인할 수 있습니다.")
    ticket.last_user_read_at = timezone.now()
    ticket.save(update_fields=["last_user_read_at", "updated_at"])
    return ticket


@transaction.atomic
def add_user_message(ticket: SupportTicket, *, user, content: str) -> SupportMessage:
    """사용자 답변을 추가하고 해결 건은 처리 중으로 재개합니다."""
    if ticket.requester_id != user.id:
        raise ValidationError("본인의 문의만 답변할 수 있습니다.")
    if ticket.status == SupportTicket.Status.CLOSED:
        raise ValidationError("종결된 문의에는 답변할 수 없습니다.")
    message = SupportMessage.objects.create(ticket=ticket, sender=user, sender_name=display_name(user), sender_kind=SupportMessage.SenderKind.USER, content=content)
    updates = {"last_user_message_at": message.created_at}
    if ticket.status == SupportTicket.Status.RESOLVED:
        updates["status"] = SupportTicket.Status.IN_PROGRESS
        updates["resolved_at"] = None
        add_event(ticket, actor=user, event_type="ticket.reopened", payload={"from": SupportTicket.Status.RESOLVED})
    SupportTicket.objects.filter(pk=ticket.pk).update(**updates)
    return message


def transition(ticket: SupportTicket, *, actor, status: str, reason: str = "") -> SupportTicket:
    """운영자 상태 전이와 감사 이벤트를 기록합니다."""
    allowed = {
        SupportTicket.Status.RECEIVED: {SupportTicket.Status.IN_PROGRESS, SupportTicket.Status.CLOSED},
        SupportTicket.Status.IN_PROGRESS: {SupportTicket.Status.WAITING_FOR_USER, SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED},
        SupportTicket.Status.WAITING_FOR_USER: {SupportTicket.Status.IN_PROGRESS, SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED},
        SupportTicket.Status.RESOLVED: {SupportTicket.Status.CLOSED, SupportTicket.Status.IN_PROGRESS},
        SupportTicket.Status.CLOSED: set(),
    }
    if status not in allowed.get(ticket.status, set()):
        raise ValidationError("허용되지 않는 문의 상태 전이입니다.")
    before = ticket.status
    ticket.status = status
    if status == SupportTicket.Status.RESOLVED:
        ticket.resolved_at = timezone.now()
    if status == SupportTicket.Status.CLOSED:
        ticket.closed_at = timezone.now()
    ticket.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])
    add_event(ticket, actor=actor, event_type="ticket.status_changed", payload={"from": before, "to": status, "reason": reason})
    return ticket


@transaction.atomic
def anonymize_user_tickets(user) -> None:
    """탈퇴자의 티켓 증적은 남기되 직접 식별자와 첨부 접근을 제거합니다."""
    from config.apps.accounts.models import DeletedAccountFile

    tickets = SupportTicket.objects.select_for_update().filter(requester=user)
    for attachment in ticket_attachment_queryset(tickets):
        if attachment.file:
            DeletedAccountFile.objects.get_or_create(name=attachment.file.name)
    ticket_attachment_queryset(tickets).delete()
    tickets.update(requester=None, requester_name="탈퇴회원", requester_role="")


def ticket_attachment_queryset(tickets):
    """주어진 티켓 집합의 첨부를 반환합니다."""
    from .models import SupportAttachment
    return SupportAttachment.objects.filter(ticket__in=tickets)


def ensure_support_conversation(*, user, role: str) -> SupportConversation:
    """실제 보유 역할에만 역할별 고객지원 대화방을 하나 보장합니다."""
    valid_roles = {
        SupportConversation.Role.STUDENT: hasattr(user, "student_profile"),
        SupportConversation.Role.INSTRUCTOR: hasattr(user, "instructor_profile"),
    }
    if not valid_roles.get(role, False):
        raise ValidationError("보유하지 않은 역할의 고객지원방은 만들 수 없습니다.")
    conversation, _ = SupportConversation.objects.get_or_create(member=user, role=role)
    return conversation


@transaction.atomic
def ensure_support_conversation_with_onboarding(*, user, role: str) -> SupportConversation:
    """역할별 고객지원방과 가입 안내 메시지를 정확히 한 번 보장합니다."""
    conversation = ensure_support_conversation(user=user, role=role)
    from config.apps.accounts.models import Instructor

    official = (
        Instructor.objects.select_related("user")
        .filter(is_official_creator=True)
        .first()
    )
    sender = official.user if official is not None else None
    templates = (
        (
            SupportConversationMessage.OnboardingTemplateKey.STUDENT_WELCOME,
            STUDENT_WELCOME_MESSAGE,
            SupportConversationMessage.ActionType.KAKAO_CUSTOMER_CENTER,
            KAKAO_CUSTOMER_CENTER_LABEL,
        ),
        (
            SupportConversationMessage.OnboardingTemplateKey.STUDENT_PAYBACK,
            STUDENT_PAYBACK_MESSAGE,
            SupportConversationMessage.ActionType.NONE,
            "",
        ),
    ) if role == SupportConversation.Role.STUDENT else (
        (
            SupportConversationMessage.OnboardingTemplateKey.INSTRUCTOR_WELCOME,
            INSTRUCTOR_WELCOME_MESSAGE,
            SupportConversationMessage.ActionType.KAKAO_CUSTOMER_CENTER,
            KAKAO_CUSTOMER_CENTER_LABEL,
        ),
    )

    for template_key, content, action_type, action_label in templates:
        message, created = SupportConversationMessage.objects.get_or_create(
            conversation=conversation,
            onboarding_template_key=template_key,
            defaults={
                "sender": sender,
                "sender_kind": SupportConversationMessage.SenderKind.OPERATOR,
                "content": content,
                "action_type": action_type,
                "action_label": action_label,
            },
        )
        if created:
            SupportConversation.objects.filter(pk=conversation.pk).update(
                last_operator_message_at=message.created_at,
                updated_at=message.created_at,
            )
    conversation.refresh_from_db()
    return conversation


def validate_conversation_action(*, conversation, action_type: str, action_target_id: int | None) -> None:
    """운영자 버튼이 수신 회원의 실제 소유 화면만 열도록 검증합니다."""
    if action_type == SupportConversationMessage.ActionType.NONE:
        if action_target_id is not None:
            raise ValidationError("동작 없는 메시지에는 대상 ID를 지정할 수 없습니다.")
        return
    if action_type == SupportConversationMessage.ActionType.CASH_HISTORY:
        if conversation.role != SupportConversation.Role.STUDENT or action_target_id is not None:
            raise ValidationError("구매 내역은 학생 고객지원방에서만 열 수 있습니다.")
        return
    if action_type == SupportConversationMessage.ActionType.KAKAO_CUSTOMER_CENTER:
        if action_target_id is not None:
            raise ValidationError("카카오 고객센터 버튼에는 대상 ID를 지정할 수 없습니다.")
        return
    if action_target_id is None:
        raise ValidationError("버튼 대상 ID가 필요합니다.")
    if action_type == SupportConversationMessage.ActionType.TUTORING_CHAT:
        from config.apps.chat_app.models import ChatRoom

        room = ChatRoom.objects.filter(pk=action_target_id).select_related("student__user", "instructor__user").first()
        if room is None or conversation.member_id not in {room.student.user_id, room.instructor.user_id}:
            raise ValidationError("회원이 참여한 과외 채팅방만 연결할 수 있습니다.")
        expected_role = "student" if room.student.user_id == conversation.member_id else "instructor"
        if expected_role != conversation.role:
            raise ValidationError("현재 고객지원 역할과 과외 채팅방 역할이 일치하지 않습니다.")
        return
    if action_type == SupportConversationMessage.ActionType.SUPPORT_TICKET:
        ticket = SupportTicket.objects.filter(pk=action_target_id, requester=conversation.member).first()
        if ticket is None or ticket.requester_role != conversation.role:
            raise ValidationError("현재 역할의 본인 문의 티켓만 연결할 수 있습니다.")
        return
    raise ValidationError("지원하지 않는 고객지원 버튼입니다.")


@transaction.atomic
def add_conversation_message(
    conversation: SupportConversation,
    *,
    sender,
    sender_kind: str,
    content: str,
    action_type: str = SupportConversationMessage.ActionType.NONE,
    action_target_id: int | None = None,
    action_label: str = "",
) -> SupportConversationMessage:
    """메시지·목록 정렬 시각·읽지 않음 기준을 원자적으로 기록합니다."""
    content = content.strip()
    if not content:
        raise ValidationError("메시지 내용을 입력해주세요.")
    if sender_kind == SupportConversationMessage.SenderKind.OPERATOR:
        validate_conversation_action(
            conversation=conversation,
            action_type=action_type,
            action_target_id=action_target_id,
        )
    elif action_type != SupportConversationMessage.ActionType.NONE:
        raise ValidationError("회원 메시지에는 버튼을 추가할 수 없습니다.")
    message = SupportConversationMessage.objects.create(
        conversation=conversation,
        sender=sender,
        sender_kind=sender_kind,
        content=content,
        action_type=action_type,
        action_target_id=action_target_id,
        action_label=action_label.strip(),
    )
    update_field = (
        "last_member_message_at"
        if sender_kind == SupportConversationMessage.SenderKind.MEMBER
        else "last_operator_message_at"
    )
    SupportConversation.objects.filter(pk=conversation.pk).update(
        **{update_field: message.created_at, "updated_at": message.created_at}
    )
    conversation.refresh_from_db()
    return message


def publish_support_conversation_message(
    conversation: SupportConversation,
    message: SupportConversationMessage,
) -> None:
    """고객지원 메시지의 실시간·채팅 푸시 후처리를 단일 경로로 수행합니다."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from .views import broadcast_conversation_event

    broadcast_conversation_event(conversation, "message", message=message)
    if message.sender_kind != SupportConversationMessage.SenderKind.OPERATOR:
        return

    member = conversation.member
    unread_messages = conversation.messages.filter(
        sender_kind=SupportConversationMessage.SenderKind.OPERATOR,
    )
    if conversation.last_member_read_at is not None:
        unread_messages = unread_messages.filter(
            created_at__gt=conversation.last_member_read_at,
        )
    unread_count = unread_messages.count()
    from config.apps.accounts.models import Instructor

    official = (
        Instructor.objects.select_related("user")
        .filter(is_official_creator=True)
        .first()
    )
    sender_name = (
        getattr(official.user, "user_name", "")
        if official is not None
        else ""
    ) or "클래씨 공식 계정"
    sender_id = str(official.user_id) if official is not None else "official"
    room_id = f"support:{conversation.pk}"
    payload = {
        "type": "chat.summary",
        "room_id": room_id,
        "msg_id": str(message.pk),
        "text": message.content,
        "created_at": message.created_at.isoformat(),
        "sender_id": sender_id,
        "sender_name": sender_name,
        "target_role": conversation.role,
        "unread_count": unread_count,
    }
    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            f"notification_user_{member.pk}",
            payload,
        )

    if conversation.is_muted:
        return
    if support_member_is_online(conversation.pk, member.pk):
        return
    tokens = list(member.device_tokens.all())
    if tokens and not any(
        token.is_active and getattr(token, "is_chat_active", True)
        for token in tokens
    ):
        return

    from config.apps.notification.fcm import send_push_to_user

    send_push_to_user(
        member,
        title=sender_name,
        body=message.content[:100] or "새 고객지원 답변이 도착했어요.",
        data={
            "type": "message",
            "room_id": room_id,
            "msg_id": str(message.pk),
            "sender_id": sender_id,
            "sender_name": sender_name,
            "created_at": message.created_at.isoformat(),
            "target_role": conversation.role,
            "unread_count": str(unread_count),
        },
        chat_only=True,
    )

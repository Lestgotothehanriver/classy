"""고객지원 WebSocket 인증에 쓰는 단기 관리자 티켓입니다."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone


TICKET_TTL_SECONDS = 60
_TICKET_KEY = "support:admin-ws-ticket:{ticket}"
_USED_TICKET_KEY = "support:admin-ws-ticket-used:{ticket}"


def issue_admin_realtime_ticket(user) -> dict[str, str]:
    """슈퍼관리자 [user]에게 한 번만 쓸 수 있는 WebSocket 티켓을 발급합니다."""
    ticket = secrets.token_urlsafe(32)
    cache.set(_TICKET_KEY.format(ticket=ticket), {"user_id": user.pk}, TICKET_TTL_SECONDS)
    expires_at = timezone.now() + timedelta(seconds=TICKET_TTL_SECONDS)
    return {"ticket": ticket, "expires_at": expires_at.isoformat()}


def consume_admin_realtime_ticket(ticket: str | None):
    """[ticket]을 원자적으로 한 번 소비하고, 유효한 슈퍼관리자를 반환합니다."""
    if not ticket:
        return None

    used_key = _USED_TICKET_KEY.format(ticket=ticket)
    if not cache.add(used_key, True, timeout=TICKET_TTL_SECONDS):
        return None

    payload = cache.get(_TICKET_KEY.format(ticket=ticket))
    cache.delete(_TICKET_KEY.format(ticket=ticket))
    if not payload:
        return None

    return get_user_model().objects.filter(
        pk=payload.get("user_id"),
        is_active=True,
        is_superuser=True,
    ).first()

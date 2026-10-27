"""예약 마케팅 FCM 캠페인의 대상 선정과 배치 발송을 담당합니다."""

import logging
from calendar import monthrange
from collections.abc import Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .fcm import _build_fcm_message, _get_fcm_app
from .models import DeviceToken, MarketingPushCampaign, MarketingPushMacro, Notification

logger = logging.getLogger(__name__)
_FCM_BATCH_SIZE = 500
_KST = ZoneInfo('Asia/Seoul')


def _target_roles(campaign: MarketingPushCampaign) -> tuple[str, ...]:
    """[campaign]의 대상 설정을 DeviceToken 역할 목록으로 변환합니다."""
    if campaign.target_role == MarketingPushCampaign.TargetRole.ALL:
        return ('student', 'instructor')
    return (campaign.target_role,)


def _target_tokens(campaign: MarketingPushCampaign) -> list[tuple[int, str, str, str]]:
    """동의·전체 알림·활성 역할 조건을 만족하는 단말 토큰을 조회합니다."""
    return list(
        DeviceToken.objects.filter(
            is_active=True,
            active_role__in=_target_roles(campaign),
            user__is_active=True,
            user__marketing_opt_in=True,
        )
        .values_list('user_id', 'active_role', 'token', 'platform')
        .order_by('id')
    )


def _chunks(values: list, size: int) -> Iterable[list]:
    """[values]를 Firebase `send_each` 제한에 맞게 [size]씩 분할합니다."""
    for index in range(0, len(values), size):
        yield values[index:index + size]


def next_macro_occurrence(
    macro: MarketingPushMacro,
    *,
    after,
) -> datetime:
    """[after]보다 엄격히 뒤인 매크로의 다음 KST 실행 시각을 계산합니다.

    매월 29~31일은 해당 월의 마지막 날에 실행해 매크로가 멈추지 않도록 합니다.
    """
    local_after = after.astimezone(_KST)
    current_date = local_after.date()

    if macro.recurrence == MarketingPushMacro.Recurrence.DAILY:
        candidate_date = current_date
        candidate = datetime.combine(candidate_date, macro.scheduled_time, tzinfo=_KST)
        if candidate <= local_after:
            candidate_date += timedelta(days=1)
        return datetime.combine(candidate_date, macro.scheduled_time, tzinfo=_KST)

    if macro.recurrence == MarketingPushMacro.Recurrence.WEEKLY:
        days_until = (macro.weekday - current_date.weekday()) % 7
        candidate_date = current_date + timedelta(days=days_until)
        candidate = datetime.combine(candidate_date, macro.scheduled_time, tzinfo=_KST)
        if candidate <= local_after:
            candidate_date += timedelta(days=7)
        return datetime.combine(candidate_date, macro.scheduled_time, tzinfo=_KST)

    requested_day = macro.day_of_month

    def monthly_date(year: int, month: int):
        return current_date.replace(
            year=year,
            month=month,
            day=min(requested_day, monthrange(year, month)[1]),
        )

    candidate_date = monthly_date(current_date.year, current_date.month)
    candidate = datetime.combine(candidate_date, macro.scheduled_time, tzinfo=_KST)
    if candidate <= local_after:
        year = current_date.year + (current_date.month == 12)
        month = 1 if current_date.month == 12 else current_date.month + 1
        candidate_date = monthly_date(year, month)
    return datetime.combine(candidate_date, macro.scheduled_time, tzinfo=_KST)


def materialize_due_marketing_macros(*, now=None) -> list[MarketingPushCampaign]:
    """기한이 지난 활성 매크로마다 발송 스냅샷 캠페인 한 건을 생성합니다.

    타이머가 멈춘 동안 누적된 과거 회차를 한 번에 몰아서 보내지 않으며, 가장 오래된
    미처리 회차만 생성한 뒤 다음 실행 시각은 현재 시각 뒤로 이동합니다.
    """
    current_time = now or timezone.now()
    macro_ids = list(
        MarketingPushMacro.objects.filter(
            is_active=True,
            next_scheduled_at__lte=current_time,
        ).values_list('id', flat=True)
    )
    campaigns = []
    for macro_id in macro_ids:
        with transaction.atomic():
            macro = (
                MarketingPushMacro.objects.select_for_update()
                .filter(
                    pk=macro_id,
                    is_active=True,
                    next_scheduled_at__lte=current_time,
                )
                .first()
            )
            if macro is None:
                continue
            campaign = MarketingPushCampaign.objects.create(
                target_role=macro.target_role,
                title=macro.title,
                body=macro.body,
                scheduled_at=macro.next_scheduled_at,
                push_only=macro.push_only,
                macro=macro,
                created_by=macro.created_by,
            )
            macro.last_dispatched_at = current_time
            macro.next_scheduled_at = next_macro_occurrence(macro, after=current_time)
            macro.save(
                update_fields=['last_dispatched_at', 'next_scheduled_at', 'updated_at']
            )
            campaigns.append(campaign)
    return campaigns


def _create_notification_center_entries(
    campaign: MarketingPushCampaign,
    token_rows: list[tuple[int, str, str, str]],
) -> int:
    """푸시와 함께 보여 줄 역할별 알림센터 항목을 중복 없이 저장합니다."""
    recipients = {(user_id, role) for user_id, role, _, _ in token_rows}
    entries = [
        Notification(
            user_id=user_id,
            type='marketing',
            role=role,
            title=campaign.title,
            body=campaign.body,
            data={'campaign_id': str(campaign.pk)},
        )
        for user_id, role in recipients
    ]
    Notification.objects.bulk_create(entries, batch_size=_FCM_BATCH_SIZE)
    return len(entries)


def _send_fcm_batches(
    campaign: MarketingPushCampaign,
    token_rows: list[tuple[int, str, str, str]],
) -> tuple[int, int]:
    """[campaign]을 최대 500개 토큰 단위로 동기 발송하고 성공·실패 수를 반환합니다."""
    if not token_rows:
        return 0, 0

    _get_fcm_app()
    from firebase_admin import messaging

    success_count = 0
    failure_count = 0
    payload = {'type': 'marketing'}
    for rows in _chunks(token_rows, _FCM_BATCH_SIZE):
        messages = [
            _build_fcm_message(token, platform, campaign.title, campaign.body, payload)
            for _, _, token, platform in rows
        ]
        response = messaging.send_each(messages)
        success_count += response.success_count
        failure_count += response.failure_count
    return success_count, failure_count


def dispatch_marketing_campaign(campaign_id: int, *, now=None) -> MarketingPushCampaign | None:
    """예약 상태인 [campaign_id]를 한 번만 점유해 FCM과 선택적 알림센터로 발송합니다.

    동일 캠페인을 동시에 처리해도 행 잠금과 상태 전이로 한 번만 발송합니다.
    """
    current_time = now or timezone.now()
    with transaction.atomic():
        campaign = (
            MarketingPushCampaign.objects.select_for_update()
            .filter(pk=campaign_id)
            .first()
        )
        if campaign is None or campaign.status != MarketingPushCampaign.Status.SCHEDULED:
            return None
        if campaign.scheduled_at > current_time:
            return None
        campaign.status = MarketingPushCampaign.Status.SENDING
        campaign.failure_detail = ''
        campaign.save(update_fields=['status', 'failure_detail', 'updated_at'])

    token_rows = _target_tokens(campaign)
    recipient_count = len({(user_id, role) for user_id, role, _, _ in token_rows})
    try:
        if not campaign.push_only:
            _create_notification_center_entries(campaign, token_rows)
        success_count, failure_count = _send_fcm_batches(campaign, token_rows)
    except Exception as error:
        logger.exception('Marketing campaign %s failed.', campaign.pk)
        campaign.status = MarketingPushCampaign.Status.FAILED
        campaign.sent_at = timezone.now()
        campaign.recipient_count = recipient_count
        campaign.token_count = len(token_rows)
        campaign.success_count = 0
        campaign.failure_count = len(token_rows)
        campaign.failure_detail = str(error)[:2000]
        campaign.save(
            update_fields=[
                'status', 'sent_at', 'recipient_count', 'token_count',
                'success_count', 'failure_count', 'failure_detail', 'updated_at',
            ]
        )
        return campaign

    campaign.status = MarketingPushCampaign.Status.COMPLETED
    campaign.sent_at = timezone.now()
    campaign.recipient_count = recipient_count
    campaign.token_count = len(token_rows)
    campaign.success_count = success_count
    campaign.failure_count = failure_count
    campaign.save(
        update_fields=[
            'status', 'sent_at', 'recipient_count', 'token_count',
            'success_count', 'failure_count', 'updated_at',
        ]
    )
    return campaign


def dispatch_due_marketing_campaigns(*, now=None) -> list[MarketingPushCampaign]:
    """현재 시각까지 예약된 마케팅 캠페인을 모두 처리합니다."""
    current_time = now or timezone.now()
    materialize_due_marketing_macros(now=current_time)
    campaign_ids = list(
        MarketingPushCampaign.objects.filter(
            status=MarketingPushCampaign.Status.SCHEDULED,
            scheduled_at__lte=current_time,
        ).values_list('id', flat=True)
    )
    return [
        campaign
        for campaign_id in campaign_ids
        if (campaign := dispatch_marketing_campaign(campaign_id, now=current_time)) is not None
    ]

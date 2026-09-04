"""Synchronize Google Play refunds and chargebacks into the cash ledger."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from config.apps.cash.google_iap import (
    GoogleIAPError,
    apply_google_voided_purchase,
    list_google_voided_purchases,
)
from config.apps.cash.models import GooglePlaySyncState


class Command(BaseCommand):
    """Reconcile voided purchases using a durable, overlapping checkpoint."""

    help = 'Synchronize Google Play voided purchases and cash debt.'

    def handle(self, *args, **options):
        """Run one bounded reconciliation pass for Render Cron."""

        end_time = timezone.now()
        state, _ = GooglePlaySyncState.objects.get_or_create(
            key='voided_purchases'
        )
        start_time = (
            state.last_synced_at - timedelta(hours=24)
            if state.last_synced_at
            else end_time - timedelta(days=30)
        )
        counts: dict[str, int] = {}
        try:
            for voided in list_google_voided_purchases(
                start_time=start_time,
                end_time=end_time,
            ):
                result = apply_google_voided_purchase(voided)
                counts[result] = counts.get(result, 0) + 1
        except GoogleIAPError as exc:
            raise CommandError(str(exc)) from exc

        state.last_synced_at = end_time
        state.save(update_fields=['last_synced_at', 'updated_at'])
        summary = ', '.join(
            f'{key}={value}' for key, value in sorted(counts.items())
        ) or 'no voided purchases'
        self.stdout.write(self.style.SUCCESS(f'Google Play sync complete: {summary}'))

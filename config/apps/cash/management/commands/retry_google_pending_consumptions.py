"""Retry Google Play purchases whose server consumption is still pending."""

import logging

from django.core.management.base import BaseCommand, CommandError

from config.apps.cash.google_iap import GoogleIAPError, consume_google_purchase
from config.apps.cash.models import GooglePlayPurchase

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Run one bounded Google Play consumption recovery pass."""

    help = 'Retry up to 100 unconsumed Google Play purchases.'

    def handle(self, *args, **options):
        """Consume pending purchases without re-granting cash."""

        pending = list(
            GooglePlayPurchase.objects
            .filter(consumption_state='NOT_CONSUMED')
            .select_related('purchase_history')
            .order_by('pk')[:100]
        )
        completed = 0
        failed = 0
        for detail in pending:
            try:
                consume_google_purchase(detail)
                completed += 1
            except GoogleIAPError as exc:
                failed += 1
                logger.warning(
                    'Google Play consume retry failed purchase_id=%s: %s',
                    detail.purchase_history_id,
                    exc,
                )

        summary = (
            f'checked={len(pending)}, completed={completed}, failed={failed}'
        )
        if failed:
            raise CommandError(f'Google Play consume retry incomplete: {summary}')
        self.stdout.write(self.style.SUCCESS(f'Google Play consume retry complete: {summary}'))

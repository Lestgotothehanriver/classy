"""예약된 마케팅 FCM 캠페인을 발송합니다."""

from django.core.management.base import BaseCommand

from config.apps.notification.marketing import dispatch_due_marketing_campaigns


class Command(BaseCommand):
    """현재 시각까지 예약된 마케팅 캠페인을 한 번 처리합니다."""

    help = '현재 시각까지 예약된 마케팅 FCM 캠페인을 발송합니다.'

    def handle(self, *args, **options):
        """처리한 캠페인 수를 표준 출력으로 반환합니다."""
        campaigns = dispatch_due_marketing_campaigns()
        self.stdout.write(self.style.SUCCESS(f'processed={len(campaigns)}'))

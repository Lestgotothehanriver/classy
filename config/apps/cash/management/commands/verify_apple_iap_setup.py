from django.core.management.base import BaseCommand, CommandError

from appstoreserverlibrary.api_client import APIException

from config.apps.cash.apple_iap import (
    AppleIAPConfigurationError,
    get_app_store_server_api_client,
    get_apple_signed_data_verifier,
)


class Command(BaseCommand):
    help = 'Validate Apple IAP configuration and optionally request a sandbox test notification.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--request-test-notification',
            action='store_true',
            help='Call App Store Server API requestTestNotification.',
        )

    def handle(self, *args, **options):
        try:
            get_apple_signed_data_verifier()
            self.stdout.write(self.style.SUCCESS('Apple signed-data verifier: OK'))

            client = get_app_store_server_api_client()
            self.stdout.write(self.style.SUCCESS('App Store Server API credentials: loaded'))
            if options['request_test_notification']:
                client.request_test_notification()
                self.stdout.write(
                    self.style.SUCCESS('App Store test notification request: accepted')
                )
        except AppleIAPConfigurationError as exc:
            raise CommandError(str(exc)) from exc
        except APIException as exc:
            raise CommandError(f'App Store Server API rejected the request: {exc}') from exc

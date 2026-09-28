from django.core.management.base import BaseCommand
from config.apps.accounts.deletion import purge_deleted_files


class Command(BaseCommand):
    help = 'Retry committed account-deletion storage jobs.'

    def handle(self, *args, **options):
        self.stdout.write(str(purge_deleted_files(limit=1000)))

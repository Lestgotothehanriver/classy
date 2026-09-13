from django.core.management.base import BaseCommand
from config.apps.accounts.models import Subject
from config.apps.tutoring.constant import REGION_CHOICES, STUDENT_SUBJECT_CHOICES
from config.apps.tutoring.models import Region


class Command(BaseCommand):
    help = 'Initialize subject and region catalogs without importing user data.'

    def handle(self, *args, **options):
        for number, name in STUDENT_SUBJECT_CHOICES:
            Subject.objects.get_or_create(number=number, defaults={'name': name})
        for number, _ in REGION_CHOICES:
            Region.objects.get_or_create(number=number)
        self.stdout.write(self.style.SUCCESS('Subject and region catalogs initialized.'))

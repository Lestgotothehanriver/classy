from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from config.apps.accounts.models import Instructor
from config.apps.cash.models import InstructorMonthlyRank

class Command(BaseCommand):
    help = 'Calculates and saves the monthly cash ranking for instructors.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, help='Year for the ranking calculation')
        parser.add_argument('--month', type=int, help='Month for the ranking calculation')

    def handle(self, *args, **options):
        now = timezone.now()
        
        target_month = options.get('month')
        target_year = options.get('year')

        # Default to previous month if not provided
        if not target_month or not target_year:
            target_month = now.month - 1
            target_year = now.year
            if target_month == 0:
                target_month = 12
                target_year -= 1

        # Delete existing ranks for this month, just in case to allow re-running
        InstructorMonthlyRank.objects.filter(year=target_year, month=target_month).delete()

        # Calculate total cash for each instructor by summing non-canceled rentals for their lectures
        instructors = Instructor.objects.annotate(
            calculated_cash=Coalesce(
                Sum(
                    'lectures__rentals__purchased_cash',
                    filter=Q(
                        lectures__rentals__created_at__year=target_year,
                        lectures__rentals__created_at__month=target_month,
                        lectures__rentals__is_canceled=False
                    )
                ), 0
            )
        ).order_by('-calculated_cash')

        ranks_to_create = []
        current_rank = 1
        
        for instructor in instructors:
            ranks_to_create.append(
                InstructorMonthlyRank(
                    year=target_year,
                    month=target_month,
                    instructor=instructor,
                    total_cash=instructor.calculated_cash,
                    rank=current_rank
                )
            )
            current_rank += 1

        # Bulk create all records
        InstructorMonthlyRank.objects.bulk_create(ranks_to_create)
        self.stdout.write(self.style.SUCCESS(f'Successfully calculated and saved ranks for {target_year}-{target_month:02d}.'))

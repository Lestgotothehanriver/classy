from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from config.apps.lecture.models import Lecture

class Command(BaseCommand):
    help = 'Delete lectures that have been soft-deleted for over 30 days'

    def handle(self, *args, **kwargs):
        threshold_date = timezone.now() - timedelta(days=30)
        
        # is_delete=True이고 deleted_at이 30일 이전인 강의 찾기
        old_deleted_lectures = Lecture.objects.filter(
            is_delete=True,
            deleted_at__lte=threshold_date
        )
        
        count = old_deleted_lectures.count()
        if count > 0:
            old_deleted_lectures.delete()  # 실제 DB 레코드 삭제 (Cascade 삭제 적용됨)
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} lectures that were soft-deleted over 30 days ago.'))
        else:
            self.stdout.write(self.style.SUCCESS('No old deleted lectures found.'))

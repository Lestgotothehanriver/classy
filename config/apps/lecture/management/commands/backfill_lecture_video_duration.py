from django.core.management.base import BaseCommand

from config.apps.lecture.models import Lecture
from config.apps.lecture.utils import extract_video_duration_seconds


class Command(BaseCommand):
    help = "Backfill lecture video_duration using ffprobe."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recalculate durations even when video_duration is already set.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )
        parser.add_argument(
            "--lecture-id",
            type=int,
            help="Backfill only one lecture id.",
        )

    def handle(self, *args, **options):
        queryset = Lecture.objects.all().order_by("id")

        lecture_id = options.get("lecture_id")
        if lecture_id is not None:
            queryset = queryset.filter(id=lecture_id)

        if not options["force"]:
            queryset = queryset.filter(video_duration=0)

        updated_count = 0
        skipped_count = 0
        failed_ids = []

        for lecture in queryset.iterator():
            duration = extract_video_duration_seconds(lecture.video)
            if duration is None:
                skipped_count += 1
                failed_ids.append(lecture.id)
                continue

            if options["dry_run"]:
                self.stdout.write(
                    f"[DRY RUN] lecture={lecture.id} duration={lecture.video_duration} -> {duration}"
                )
                updated_count += 1
                continue

            lecture.video_duration = duration
            lecture.save(update_fields=["video_duration"])
            updated_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated lecture={lecture.id} video_duration={duration}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. updated={updated_count}, skipped={skipped_count}"
            )
        )
        if failed_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"Could not extract duration for lecture ids: {failed_ids}"
                )
            )

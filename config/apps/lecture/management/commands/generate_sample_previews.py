from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from config.apps.lecture.models import Lecture
from config.apps.lecture.utils import (
    calculate_sample_preview_duration_seconds,
    create_sample_preview,
    extract_video_duration_seconds,
)


class Command(BaseCommand):
    """Generate missing A-specific sample clips for existing paid lectures."""

    help = "Generate sample previews for active paid lectures."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Replace existing sample previews.")
        parser.add_argument("--lecture-id", type=int, action="append", dest="lecture_ids")

    def handle(self, *args, **options):
        queryset = Lecture.objects.filter(
            price__gt=0,
            is_preview=False,
            is_active=True,
            is_delete=False,
            admin_blocked_at__isnull=True,
        ).order_by("id")
        if options["lecture_ids"]:
            queryset = queryset.filter(id__in=options["lecture_ids"])

        generated = skipped = failed = 0
        failed_ids = []
        for lecture in queryset.iterator():
            if lecture.sample_preview and not options["force"]:
                skipped += 1
                continue
            old_preview_name = lecture.sample_preview.name if lecture.sample_preview else ""
            try:
                duration = extract_video_duration_seconds(lecture.video)
                if duration is None:
                    raise ValueError("원본 길이를 확인할 수 없습니다.")
                preview_duration = calculate_sample_preview_duration_seconds(duration)
                preview, cleanup = create_sample_preview(lecture.video, preview_duration)
                try:
                    lecture.sample_preview.save(preview.name, preview, save=False)
                    lecture.video_duration = duration
                    lecture.sample_preview_duration = preview_duration
                    lecture.save(
                        update_fields=[
                            "sample_preview",
                            "sample_preview_duration",
                            "video_duration",
                        ]
                    )
                finally:
                    cleanup()
                if old_preview_name and old_preview_name != lecture.sample_preview.name:
                    default_storage.delete(old_preview_name)
                generated += 1
                self.stdout.write(self.style.SUCCESS(f"generated lecture={lecture.id}"))
            except Exception as exc:
                failed += 1
                failed_ids.append(lecture.id)
                self.stderr.write(self.style.ERROR(f"failed lecture={lecture.id}: {exc}"))

        self.stdout.write(
            f"sample previews: generated={generated} skipped={skipped} failed={failed}"
        )
        if failed_ids:
            lecture_id_args = " ".join(
                f"--lecture-id {lecture_id}" for lecture_id in failed_ids
            )
            self.stderr.write(
                self.style.WARNING(
                    "retry failed lectures with: "
                    f"python manage.py generate_sample_previews {lecture_id_args}"
                )
            )

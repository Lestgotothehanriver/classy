from django.core.management.base import BaseCommand
from config.apps.chat_app.notifications import push_to_all


class Command(BaseCommand):
    help = "전체 유저에게 공지 푸시 알림 발송"

    def add_arguments(self, parser):
        parser.add_argument("--title", required=True, help="알림 제목")
        parser.add_argument("--body", required=True, help="알림 내용")

    def handle(self, *args, **options):
        title = options["title"]
        body = options["body"]
        self.stdout.write(f"발송 중... 제목: {title}")
        result = push_to_all(title=title, body=body, data={"type": "announcement"})
        self.stdout.write(
            self.style.SUCCESS(
                f"완료 — 성공: {result['success']}, 실패: {result['failure']}"
            )
        )
        if result.get("errors"):
            for err in result["errors"]:
                self.stdout.write(self.style.WARNING(f"  실패 토큰: {err}"))
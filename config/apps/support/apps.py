from django.apps import AppConfig


class SupportConfig(AppConfig):
    """1:1 문의 티켓 앱 설정입니다."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.support"

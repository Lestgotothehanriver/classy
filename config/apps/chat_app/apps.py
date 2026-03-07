from django.apps import AppConfig


class ChatAppConfig(AppConfig):
    name = "config.apps.chat_app"  # 실제 앱 경로명으로
    default_auto_field = 'django.db.models.BigAutoField'
    def ready(self):
        from . import signals  # noqa: F401
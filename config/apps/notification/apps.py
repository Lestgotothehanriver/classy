from django.apps import AppConfig


class NotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.notification"

    def ready(self):
        from . import signals  # noqa

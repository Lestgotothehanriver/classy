from django.apps import AppConfig


class NotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.notification"

    def ready(self):
        import config.apps.notification.signals  # noqa: F401

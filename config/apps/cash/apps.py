from django.apps import AppConfig


class CashConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.cash"

    def ready(self):
        # Register deployment checks for Apple IAP configuration.
        from . import checks  # noqa: F401

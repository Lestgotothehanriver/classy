from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.accounts"

    def ready(self):
        import config.apps.common.signals

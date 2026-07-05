from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.accounts"

    def ready(self):
        import config.apps.common.signals
        
        # Apply absolute URL monkeypatches for media/lecture files
        from config.apps.common.monkeypatches import apply_patches
        apply_patches()

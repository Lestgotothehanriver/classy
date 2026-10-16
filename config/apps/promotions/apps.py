from django.apps import AppConfig


class PromotionsConfig(AppConfig):
    """출시 프로모션 앱 설정입니다."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "config.apps.promotions"
    label = "promotions"

"""Limited signup fixtures for App Review; not used for password reset or phone changes."""
import re
from django.conf import settings
from django.contrib.auth import get_user_model


def review_signup_code(phone):
    normalized = re.sub(r"\D", "", str(phone or ""))
    allowed = getattr(settings, "APP_REVIEW_SIGNUP_PHONES", ())
    code = getattr(settings, "APP_REVIEW_SIGNUP_CODE", "")
    if normalized not in allowed or not re.fullmatch(r"[0-9]{6}", code):
        return None
    # Fail closed if a configured number is ever associated with a real account.
    variants = {normalized}
    if len(normalized) == 11:
        variants.add(f"{normalized[:3]}-{normalized[3:7]}-{normalized[7:]}")
    if get_user_model().objects.filter(phone__in=variants).exclude(iap_environment="SANDBOX").exists():
        return None
    return code

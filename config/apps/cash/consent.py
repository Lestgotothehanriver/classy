"""Cash-terms consent helpers shared by API and purchase verification."""

from django.conf import settings

from config.apps.accounts.models import UserConsent


def current_cash_terms_version() -> str:
    """Return the server-authoritative cash terms version."""
    return str(getattr(settings, 'POLICY_VERSIONS', {}).get('cash_terms', ''))


def has_current_cash_terms_consent(user) -> bool:
    """Return whether [user] has agreed to the currently published version."""
    version = current_cash_terms_version()
    return bool(version) and UserConsent.objects.filter(
        user=user,
        doc_type=UserConsent.DOC_CASH_TERMS,
        version=version,
        agreed=True,
    ).exists()


def record_cash_terms_consent(user, *, version: str) -> UserConsent:
    """Append one current-version cash-terms consent record for [user]."""
    current_version = current_cash_terms_version()
    if not current_version or version != current_version:
        raise ValueError('Cash terms version is no longer current.')
    existing = UserConsent.objects.filter(
        user=user,
        doc_type=UserConsent.DOC_CASH_TERMS,
        version=current_version,
        agreed=True,
    ).first()
    if existing:
        return existing
    return UserConsent.objects.create(
        user=user,
        user_email=user.email,
        doc_type=UserConsent.DOC_CASH_TERMS,
        version=current_version,
        agreed=True,
    )

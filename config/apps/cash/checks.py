from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def apple_iap_deployment_checks(app_configs, **kwargs):
    messages = []
    severity = Warning if settings.DEBUG else Error

    required = {
        'APPLE_BUNDLE_ID': settings.APPLE_BUNDLE_ID,
        'APPLE_IAP_ISSUER_ID': settings.APPLE_IAP_ISSUER_ID,
        'APPLE_IAP_KEY_ID': settings.APPLE_IAP_KEY_ID,
        'APPLE_IAP_PRIVATE_KEY_BASE64': settings.APPLE_IAP_PRIVATE_KEY_BASE64,
    }
    if settings.APPLE_IAP_ENVIRONMENT == 'PRODUCTION':
        required['APPLE_APP_ID'] = settings.APPLE_APP_ID

    for name, value in required.items():
        if not value:
            messages.append(
                severity(
                    f'{name} is not configured for Apple IAP.',
                    id=f'cash.IAP_{name}',
                )
            )

    if settings.APPLE_IAP_ENVIRONMENT not in {'SANDBOX', 'PRODUCTION'}:
        messages.append(
            Error(
                'APPLE_IAP_ENVIRONMENT must be SANDBOX or PRODUCTION.',
                id='cash.IAP_INVALID_ENVIRONMENT',
            )
        )

    for certificate in settings.APPLE_IAP_ROOT_CERTIFICATES:
        if not Path(certificate).is_file():
            messages.append(
                Error(
                    f'Apple IAP root certificate is missing: {Path(certificate).name}',
                    id='cash.IAP_MISSING_ROOT_CERTIFICATE',
                )
            )
    return messages

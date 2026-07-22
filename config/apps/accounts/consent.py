"""동의 기록 서비스.

가입/재동의/철회 등 여러 진입점에서 재사용할 수 있도록 독립 함수로 분리한다.
현재는 가입 시리얼라이저에서 호출하지만, 향후 재동의/철회 엔드포인트가 그대로 재사용한다.
"""
from django.conf import settings
from django.utils import timezone

from .models import UserConsent


def record_consent(
    user,
    *,
    terms_version=None,
    privacy_version=None,
    agreed_marketing=False,
    source="signup",
):
    """필수 동의(약관·개인정보)와 선택 동의(마케팅)를 기록한다.

    - 약관/개인정보: 항상 동의(agreed=True) 행을 append. 버전 미지정 시 서버의
      현재 버전(POLICY_VERSIONS)을 권위값으로 사용한다.
    - 마케팅: 동의한 경우에만 이력 행을 append하고, User.marketing_opt_in 플래그를 갱신한다.

    동의 주체는 UserConsent.user(FK)로 이미 식별되므로 IP 등 추가 개인정보는 수집하지 않는다.

    Returns: 생성된 UserConsent 리스트.
    """
    versions = getattr(settings, "POLICY_VERSIONS", {})
    now = timezone.now()

    created = [
        UserConsent.objects.create(
            user=user,
            doc_type=UserConsent.DOC_TERMS,
            version=terms_version or versions.get("terms", ""),
            agreed=True,
            agreed_at=now,
        ),
        UserConsent.objects.create(
            user=user,
            doc_type=UserConsent.DOC_PRIVACY,
            version=privacy_version or versions.get("privacy", ""),
            agreed=True,
            agreed_at=now,
        ),
    ]

    agreed_marketing = bool(agreed_marketing)
    if agreed_marketing:
        created.append(
            UserConsent.objects.create(
                user=user,
                doc_type=UserConsent.DOC_MARKETING,
                version=versions.get("marketing", ""),
                agreed=True,
                agreed_at=now,
            )
        )
    if user.marketing_opt_in != agreed_marketing:
        user.marketing_opt_in = agreed_marketing
        user.save(update_fields=["marketing_opt_in"])

    return created

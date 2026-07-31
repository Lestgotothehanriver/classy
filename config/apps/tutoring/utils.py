from config.apps.tutoring.constant import REGION_CHOICES


def filter_posts_by_account_region(queryset, user):
    """
    강사의 계정 거주지와 같은 광역 지역의 희망 지역을 가진 공고만 반환합니다.

    계정 지역이 비어 있거나 지원 지역에 해당 광역 지역이 없으면 전국 공고로
    폴백하지 않고 빈 QuerySet을 반환합니다.
    """
    account_region = (getattr(user, "region", "") or "").strip()
    if not account_region:
        return queryset.none()

    broad_region = account_region.split()[0].strip()
    matching_region_numbers = [
        number
        for number, label in REGION_CHOICES
        if label.strip().split()[0] == broad_region
    ]
    if not matching_region_numbers:
        return queryset.none()

    return queryset.filter(
        regions__number__in=matching_region_numbers,
    ).distinct()

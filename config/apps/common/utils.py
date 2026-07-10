import logging
from django.db.models import Count

logger = logging.getLogger(__name__)

def parse_int_list(value):
    """
    콤마로 구분된 문자열을 정수 리스트로 변환합니다.
    
    Args:
        value (str): "1,2,3" 형태의 문자열
        
    Returns:
        list[int]: 변환된 정수 리스트. 값이 없거나 형식이 잘못된 경우 빈 리스트 반환.
    """
    if not value:
        return []
    try:
        return [int(x) for x in value.split(",") if x.strip().isdigit()]
    except Exception as e:
        logger.error(f"Error parsing int list: {value}, error: {e}")
        return []

def has_field(model_cls, field_name):
    """
    모델 클래스에 특정 필드가 존재하는지 확인합니다.
    """
    return any(f.name == field_name for f in model_cls._meta.get_fields())

def order_by_likes(qs, model_cls):
    """
    좋아요 수를 기준으로 QuerySet을 정렬합니다.
    """
    field_names = {f.name for f in model_cls._meta.get_fields()}

    if "like_count" in field_names:
        return qs.order_by("-like_count", "-id")

    for candidate in ["likes", "liked_by", "like_users"]:
        if candidate in field_names:
            return qs.annotate(
                like_count=Count(candidate, distinct=True)
            ).order_by("-like_count", "-id")

    return qs.order_by("-id")

def apply_subject_filter(qs, owner_model, subject_ids, prefix=""):
    """
    과목(Subject) ID 리스트를 기반으로 QuerySet에 필터를 적용합니다.
    """
    if not subject_ids:
        return qs
    key = f"{prefix}subjects__number__in"
    return qs.filter(**{key: subject_ids}).distinct()

def get_absolute_media_url(url_or_file, request=None):
    """
    미디어 파일 객체 또는 상대경로 URL을 받아 절대경로 URL을 반환합니다.
    """
    if not url_or_file:
        return None

    # url_or_file이 FieldFile 객체 등일 수 있으므로 .url 속성 확인
    url = getattr(url_or_file, "url", url_or_file)
    if not url:
        return None

    if url.startswith("http://") or url.startswith("https://"):
        return url

    if request:
        absolute_url = request.build_absolute_uri(url)
        if request.is_secure() or request.META.get('HTTP_X_FORWARDED_PROTO') == 'https':
            if absolute_url.startswith("http://"):
                absolute_url = absolute_url.replace("http://", "https://", 1)
        return absolute_url

    from django.conf import settings
    base_url = getattr(settings, "BASE_URL", "http://localhost:8000")
    if not url.startswith("/"):
        url = "/" + url
    absolute_url = f"{base_url.rstrip('/')}{url}"
    if base_url.startswith("https://") and absolute_url.startswith("http://"):
        absolute_url = absolute_url.replace("http://", "https://", 1)
    return absolute_url


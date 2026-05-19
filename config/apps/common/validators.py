def validate_cost_unit(value):
    """1000 미만 값은 만원 단위로 변환합니다."""
    if value is not None and 0 < value < 1000:
        return value * 10000
    return value

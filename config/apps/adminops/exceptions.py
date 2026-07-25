class AdminOpsError(Exception):
    """관리자 운영 서비스 계층의 도메인 에러 기반 클래스입니다.

    뷰는 이 에러를 잡아 `default_status` 로 응답을 변환합니다.
    """

    default_status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AdminOpsError):
    """입력값이 유효하지 않을 때(예: 반려 사유 누락)."""

    default_status = 400


class ConflictError(AdminOpsError):
    """현재 상태에서 허용되지 않는 전이일 때(예: 비-PENDING 승인)."""

    default_status = 409

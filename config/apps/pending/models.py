from django.conf import settings
from django.db import models
from config.apps.accounts.models import Instructor
from django.core.validators import FileExtensionValidator

class PendingInstructor(models.Model):
    """
    강사 인증 대기 모델.
    - Instructor과 1:1 관계로 연결
    - 인증 대기 중인 강사의 추가 정보를 저장 (ex: 제출한 서류, 신청 날짜 등)
    """

    instructor_profile = models.OneToOneField(
        Instructor,
        on_delete=models.CASCADE,
        related_name="pending_info",
    )
    
    # 예시: 신청 날짜
    applied_at = models.DateTimeField(auto_now_add=True)

    class Status(models.TextChoices):
        PENDING = "PENDING", "인증대기"
        VERIFIED = "VERIFIED", "인증완료"
        SUSPENDED = "SUSPENDED", "정지"

    # 강사 상태 (인증대기/완료/정지)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # 반려 사유 (인증이 반려된 경우 입력 및 조회)
    rejection_reason = models.TextField(blank=True, default="")


    def __str__(self):
        return f"PendingInstructor: {self.instructor_profile.user.username}"


class File(models.Model):
    pending_file = models.FileField(
        upload_to="files/",
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "png"])]
    )
    pending_instructor = models.ForeignKey(PendingInstructor, on_delete=models.CASCADE, related_name="files")
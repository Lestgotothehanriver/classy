import os

from rest_framework import serializers

from config.apps.pending.models import File, PendingInstructor


def _real_name(user) -> str:
    """한국식 성+이름(last_name+first_name)을 조합합니다.

    실명 필드가 별도로 없어 last_name·first_name 을 붙여 사용하고,
    둘 다 비어 있으면 닉네임(user_name)으로 폴백합니다.
    """
    name = f"{user.last_name}{user.first_name}".strip()
    return name or user.user_name


class VerificationDocumentSerializer(serializers.Serializer):
    """제출 문서 메타데이터입니다. raw 미디어 URL 은 노출하지 않습니다."""

    id = serializers.IntegerField()
    filename = serializers.SerializerMethodField()
    extension = serializers.SerializerMethodField()

    def get_filename(self, obj: File) -> str:
        return os.path.basename(obj.pending_file.name)

    def get_extension(self, obj: File) -> str:
        name = obj.pending_file.name
        return name.rsplit(".", 1)[-1].lower() if "." in name else ""


class InstructorVerificationListSerializer(serializers.ModelSerializer):
    """학력 인증 목록 항목입니다."""

    real_name = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    university = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    student_number = serializers.SerializerMethodField()
    file_count = serializers.SerializerMethodField()

    class Meta:
        model = PendingInstructor
        fields = [
            "id",
            "status",
            "applied_at",
            "reviewed_at",
            "real_name",
            "user_name",
            "email",
            "university",
            "department",
            "student_number",
            "file_count",
        ]

    def _user(self, obj: PendingInstructor):
        return obj.instructor_profile.user

    def get_real_name(self, obj: PendingInstructor) -> str:
        return _real_name(self._user(obj))

    def get_user_name(self, obj: PendingInstructor) -> str:
        return self._user(obj).user_name

    def get_email(self, obj: PendingInstructor) -> str:
        return self._user(obj).email

    def get_university(self, obj: PendingInstructor) -> str:
        return obj.instructor_profile.university

    def get_department(self, obj: PendingInstructor) -> str:
        return obj.instructor_profile.department

    def get_student_number(self, obj: PendingInstructor) -> str:
        return obj.instructor_profile.student_number

    def get_file_count(self, obj: PendingInstructor) -> int:
        annotated = getattr(obj, "file_count", None)
        return annotated if annotated is not None else obj.files.count()


class InstructorVerificationDetailSerializer(InstructorVerificationListSerializer):
    """상세 화면용. 반려 사유·처리자·문서 목록을 포함합니다."""

    reviewed_by = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta(InstructorVerificationListSerializer.Meta):
        fields = InstructorVerificationListSerializer.Meta.fields + [
            "rejection_reason",
            "reviewed_by",
            "documents",
        ]

    def get_reviewed_by(self, obj: PendingInstructor):
        return obj.reviewed_by.email if obj.reviewed_by_id else None

    def get_documents(self, obj: PendingInstructor):
        return VerificationDocumentSerializer(obj.files.all(), many=True).data


class VerificationRejectSerializer(serializers.Serializer):
    """반려 입력. 사유는 필수입니다."""

    reason = serializers.CharField()

    def validate_reason(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("반려 사유를 입력해야 합니다.")
        return value

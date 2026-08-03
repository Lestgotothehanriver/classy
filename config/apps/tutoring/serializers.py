from rest_framework import serializers
from django.db.models import Avg, Count
from django.utils import timezone
from django.conf import settings

from config.apps.accounts.models import Instructor, Student, Subject
from config.apps.pending.models import PendingInstructor
from .models import (
    TutoringPost,
    InstructorInfo,
    InstructorReview,
    StudentReview,
    TutoringResource,
    TutoringProposal,
    Region,
    requires_student_field,
)
from config.apps.common.serializers import M2MSyncMixin, AbsoluteFileField, AbsoluteImageField
from config.apps.common.utils import get_absolute_media_url
from config.apps.common.validators import validate_cost_unit

# ════════════════════════════════════════════════════════════════════════════════
# 공통 Serializer
# ════════════════════════════════════════════════════════════════════════════════

class SafeModelSerializer(serializers.ModelSerializer):
    """
    민감한 정보(password 등)를 제외하고 데이터를 직렬화하는 베이스 Serializer입니다.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in [
            "password",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
            "last_login",
        ]:
            self.fields.pop(name, None)


class SubjectSimpleSerializer(serializers.ModelSerializer):
    """
    과목 정보를 간단히 직렬화합니다.
    """
    label = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ["number", "label"]

    def get_label(self, obj):
        return str(obj)


class RegionSimpleSerializer(serializers.ModelSerializer):
    """
    지역 정보를 간단히 직렬화합니다.
    """
    label = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ["id", "label"]

    def get_label(self, obj):
        return str(obj)


def extract_subject_numbers(owner_obj):
    """
    Student/Instructor의 subjects M2M 필드에서 Subject number 목록을 반환합니다.
    """
    if hasattr(owner_obj, 'subjects'):
        return list(owner_obj.subjects.values_list("number", flat=True))
    return []


def get_instructor_verification_status(instructor):
    """Return the public verification state without collapsing PENDING."""
    pending_info = getattr(instructor, "pending_info", None)
    if pending_info is None:
        return "NOT_SUBMITTED"
    return pending_info.status


# ════════════════════════════════════════════════════════════════════════════════
# 강사 관련 Serializer
# ════════════════════════════════════════════════════════════════════════════════

class InstructorListSerializer(SafeModelSerializer):
    """
    강사 목록 조회를 위한 Serializer입니다.
    """
    subjects = serializers.SerializerMethodField()
    like_count = serializers.IntegerField(read_only=True, default=0)
    is_liked = serializers.BooleanField(read_only=True, default=False)
    average_rate = serializers.FloatField(read_only=True, default=None, allow_null=True)
    review_count = serializers.IntegerField(read_only=True, default=0)
    current_rank = serializers.IntegerField(read_only=True, default=None, allow_null=True)
    tutoring_count = serializers.IntegerField(read_only=True, default=0)
    average_cost = serializers.FloatField(read_only=True, default=None, allow_null=True)
    tutoring_count_display = serializers.SerializerMethodField()
    average_cost_display = serializers.SerializerMethodField()
    average_rate_display = serializers.SerializerMethodField()
    current_rank_display = serializers.SerializerMethodField()
    sex = serializers.CharField(source='user.sex', read_only=True)
    region = serializers.CharField(source='user.region', read_only=True)
    user_name = serializers.CharField(source='user.user_name', read_only=True)
    birth_date = serializers.DateField(source='user.birth_date', read_only=True)
    profile_image = AbsoluteImageField(source='user.profile_image', read_only=True)
    verification_status = serializers.SerializerMethodField()
    is_certified = serializers.SerializerMethodField()
    is_unverified = serializers.SerializerMethodField()

    class Meta:
        model = Instructor
        fields = [
            'id', 'user', 'university', 'department', 'created_at', 
            'instruction', 'student_number', 'is_tutoring', 'last_login', 
            'subjects', 'like_count', 'is_liked', 'average_rate', 
            'review_count', 'current_rank', 'tutoring_count', 'average_cost',
            'tutoring_count_display', 'average_cost_display',
            'average_rate_display', 'current_rank_display', 'sex', 'region',
            'user_name', 'birth_date', 'profile_image',
            'verification_status', 'is_certified', 'is_unverified'
        ]

    def get_subjects(self, obj):
        return extract_subject_numbers(obj)

    def get_verification_status(self, obj):
        return get_instructor_verification_status(obj)

    def get_is_certified(self, obj):
        return self.get_verification_status(obj) == PendingInstructor.Status.VERIFIED

    def get_is_unverified(self, obj):
        return not self.get_is_certified(obj)

    def get_tutoring_count_display(self, obj):
        count = getattr(obj, "tutoring_count", 0)
        return f"{count}건" if count else "-"

    def get_average_cost_display(self, obj):
        value = getattr(obj, "average_cost", None)
        return round(value) if value is not None else "-"

    def get_average_rate_display(self, obj):
        value = getattr(obj, "average_rate", None)
        return round(value, 2) if value is not None else "-"

    def get_current_rank_display(self, obj):
        value = getattr(obj, "current_rank", None)
        return value if value is not None else "-"


class InstructorInfoSerializer(serializers.ModelSerializer):
    """
    강사의 상세 과외 정보를 직렬화합니다.
    """
    subjects = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()
    instruction = serializers.CharField(source='instructor.instruction', read_only=True)
    verification_status = serializers.SerializerMethodField()
    is_certified = serializers.SerializerMethodField()
    is_unverified = serializers.SerializerMethodField()
    cost_display = serializers.SerializerMethodField()

    class Meta:
        model = InstructorInfo
        fields = [
            'id', 'instructor', 'cost', 'schedule', 'method', 
            'location', 'etc', 'subjects', 'regions', 'instruction',
            'verification_status', 'is_certified', 'is_unverified',
            'cost_display',
        ]

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data

    def get_regions(self, obj):
        return RegionSimpleSerializer(obj.regions.all(), many=True).data

    def get_verification_status(self, obj):
        return get_instructor_verification_status(obj.instructor)

    def get_is_certified(self, obj):
        return self.get_verification_status(obj) == PendingInstructor.Status.VERIFIED

    def get_is_unverified(self, obj):
        return not self.get_is_certified(obj)

    def get_cost_display(self, obj):
        return obj.cost if obj.cost is not None else "협의 후 결정"


def _review_resource_subjects(review):
    resource = getattr(review, "resource", None)
    if resource is not None:
        return resource.subject.all()
    return review.subjects.all()


def _review_class_type(review):
    resource = getattr(review, "resource", None)
    return getattr(resource, "class_type", None) or None


class InstructorReviewSerializer(serializers.ModelSerializer):
    """
    강사에 대한 리뷰를 직렬화합니다.
    """
    student_id = serializers.IntegerField(source="student.id", read_only=True)
    student_label = serializers.SerializerMethodField()
    student_profile_image = AbsoluteImageField(
        source="student.user.profile_image",
        read_only=True,
    )
    student_region = serializers.CharField(
        source="student.user.region",
        read_only=True,
    )
    class_type = serializers.SerializerMethodField()
    subjects = serializers.SerializerMethodField()

    class Meta:
        model = InstructorReview
        fields = [
            'id', 'resource', 'instructor', 'student', 'professionalism',
            'teaching_skill', 'punctuality', 'comment', 'created_at', 
            'subjects', 'student_id', 'student_label',
            'student_profile_image', 'student_region', 'class_type'
        ]

    def get_student_label(self, obj):
        user = getattr(obj.student, "user", None)
        return getattr(user, "user_name", None) or "학생"

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(
            _review_resource_subjects(obj),
            many=True,
        ).data

    def get_class_type(self, obj):
        return _review_class_type(obj)


# ____________________________________________________________________________________
# 강사 페이지: 공고 리스트/세부 (TutoringPost)
# ____________________________________________________________________________________
class StudentPublicSerializer(SafeModelSerializer):
    subjects = serializers.SerializerMethodField()
    avg_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Student
        fields = [
            'id', 'user', 'subjects', 'last_login', 'created_at', 
            'avg_rating', 'review_count'
        ]

    def get_subjects(self, obj):
        return extract_subject_numbers(obj)


class TutoringPostListSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.user_name', read_only=True)
    student_id = serializers.IntegerField(source='student.id', read_only=True)
    student_profile_image = AbsoluteImageField(source='student.user.profile_image', read_only=True)
    student_age = serializers.SerializerMethodField()
    student_sex = serializers.CharField(source='student.user.sex', read_only=True)
    student_field = serializers.CharField(source='field', read_only=True)
    like_count = serializers.IntegerField(read_only=True, default=0)
    subjects = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()

    class Meta:
        model = TutoringPost
        fields = [
            'id',
            'student_id',
            'student_name',
            'student_profile_image',
            'student_age',
            'student_sex',
            'student_field',
            'grade',
            'regions',
            'subjects',
            'cost',
            'method',
            'like_count',
            'is_active',
            'created_at'
        ]

    def get_student_age(self, obj):
        from django.utils import timezone
        if obj.student.user.birth_date:
            today = timezone.now().date()
            birth = obj.student.user.birth_date
            return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        return None

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data

    def get_regions(self, obj):
        return RegionSimpleSerializer(obj.regions.all(), many=True).data


class TutoringPostDetailSerializer(serializers.ModelSerializer):
    student = StudentPublicSerializer(read_only=True)
    subjects = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()

    class Meta:
        model = TutoringPost
        fields = [
            'id', 'student', 'title', 'sex', 'age', 'grade', 'field', 
            'subjects', 'method', 'regions', 'cost', 'schedule', 
            'situation', 'etc', 'is_active', 'view_count', 'created_at'
        ]

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data

    def get_regions(self, obj):
        return RegionSimpleSerializer(obj.regions.all(), many=True).data


# ____________________________________________________________________________________
# 강사 페이지: 학생 리뷰(StudentReview)
# ____________________________________________________________________________________
class StudentReviewSerializer(serializers.ModelSerializer):
    instructor_id = serializers.IntegerField(source="instructor.id", read_only=True)
    instructor_label = serializers.SerializerMethodField()
    instructor_nickname = serializers.CharField(source="instructor.user.user_name", read_only=True)
    instructor_profile_image = AbsoluteImageField(
        source="instructor.user.profile_image",
        read_only=True,
    )
    instructor_university = serializers.CharField(source="instructor.university", read_only=True)
    instructor_department = serializers.CharField(source="instructor.department", read_only=True)
    instructor_student_number = serializers.CharField(source="instructor.student_number", read_only=True)
    class_type = serializers.SerializerMethodField()
    subjects = serializers.SerializerMethodField()
    instructor_subjects = serializers.SerializerMethodField()

    class Meta:
        model = StudentReview
        fields = [
            'id', 'resource', 'student', 'instructor', 'rating', 'comment',
            'created_at',
            'instructor_id', 'instructor_label', 'instructor_nickname', 
            'instructor_profile_image',
            'instructor_university', 'instructor_department', 
            'instructor_student_number', 'class_type', 'subjects',
            'instructor_subjects'
        ]

    def get_instructor_label(self, obj):
        return str(obj.instructor)

    def get_instructor_subjects(self, obj):
        if obj.resource_id:
            return self.get_subjects(obj)
        return SubjectSimpleSerializer(obj.instructor.subjects.all(), many=True).data

    def get_subjects(self, obj):
        if obj.resource_id:
            return SubjectSimpleSerializer(
                obj.resource.subject.all(),
                many=True,
            ).data
        return SubjectSimpleSerializer(
            obj.instructor.subjects.all(),
            many=True,
        ).data

    def get_class_type(self, obj):
        return _review_class_type(obj)


# ____________________________________________________________________________________
# Write Serializers — Create / Patch 용 (subjects/regions는 number 리스트로 받아 M2M set)
# ____________________________________________________________________________________

def _sync_m2m(manager, model_cls, numbers):
    """number 리스트 → 객체 리스트로 변환 후 M2M set."""
    objs = [model_cls.objects.get_or_create(number=n)[0] for n in numbers]
    manager.set(objs)


class InstructorInfoWriteSerializer(M2MSyncMixin, serializers.ModelSerializer):
    """
    강사 과외정보 생성/수정용.
    subjects: Subject.number 리스트, regions: Region.number 리스트
    """
    m2m_fields = {'subjects': Subject, 'regions': Region}
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    regions  = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = InstructorInfo
        exclude = ["instructor"]

    def validate_cost(self, value):
        return validate_cost_unit(value)

    def to_representation(self, instance):
        # POST/PATCH 응답도 GET /mine/과 같은 완전한 형태로 반환한다.
        # write_only인 subjects/regions가 응답에서 사라지면 클라이언트가
        # 저장 직후 수정 폼을 다시 구성할 수 없다.
        return InstructorInfoSerializer(instance, context=self.context).data


class InstructorReviewWriteSerializer(serializers.ModelSerializer):
    """성사 리소스에 연결된 강사 리뷰 생성/수정용."""
    comment = serializers.CharField(
        allow_blank=False,
        max_length=500,
        trim_whitespace=True,
    )
    resource = serializers.PrimaryKeyRelatedField(
        queryset=TutoringResource.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = InstructorReview
        fields = [
            'id', 'resource', 'instructor', 'student', 'professionalism',
            'teaching_skill', 'punctuality', 'comment', 'created_at', 
        ]
        read_only_fields = ["student"]

    def validate_professionalism(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("전문성 점수는 1에서 5 사이여야 합니다.")
        return value

    def validate_teaching_skill(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("강의력 점수는 1에서 5 사이여야 합니다.")
        return value

    def validate_punctuality(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("시간 준수 점수는 1에서 5 사이여야 합니다.")
        return value

    def validate(self, attrs):
        resource = attrs.get("resource") or getattr(self.instance, "resource", None)
        if resource is None:
            if self.instance is not None and self.instance.resource_id is None:
                return super().validate(attrs)
            raise serializers.ValidationError(
                {"resource": "성사 등록된 수업 리소스가 필요합니다."}
            )
        if (
            self.instance is not None
            and self.instance.resource_id is not None
            and self.instance.resource_id != resource.pk
        ):
            raise serializers.ValidationError(
                {"resource": "리뷰가 연결된 수업은 변경할 수 없습니다."}
            )
        if resource.fee_payment_status != "PAID":
            raise serializers.ValidationError(
                {"resource": "운영 확인이 완료된 수업만 리뷰할 수 있습니다."}
            )
        duplicate_reviews = InstructorReview.objects.filter(resource=resource)
        if self.instance is not None:
            duplicate_reviews = duplicate_reviews.exclude(pk=self.instance.pk)
        if duplicate_reviews.exists():
            raise serializers.ValidationError(
                {"resource": "이 수업에는 이미 작성한 리뷰가 있습니다."}
            )

        request = self.context.get("request")
        if request is not None and resource.student.user_id != request.user.id:
            raise serializers.ValidationError(
                {"resource": "본인이 수강한 수업만 리뷰할 수 있습니다."}
            )

        instructor = attrs.get("instructor") or getattr(
            self.instance,
            "instructor",
            None,
        )
        if instructor is None or instructor.pk != resource.instructor_id:
            raise serializers.ValidationError(
                {"instructor": "수업 리소스의 선생님과 일치하지 않습니다."}
            )
        attrs["resource"] = resource
        return super().validate(attrs)

    def create(self, validated_data):
        review = super().create(validated_data)
        review.subjects.set(review.resource.subject.all())
        return review

    def update(self, instance, validated_data):
        review = super().update(instance, validated_data)
        if review.resource_id is not None:
            review.subjects.set(review.resource.subject.all())
        return review


class TutoringPostWriteSerializer(M2MSyncMixin, serializers.ModelSerializer):
    """
    과외 공고 생성/수정용.
    subjects: Subject.number 리스트, regions: Region.number 리스트
    """
    m2m_fields = {'subjects': Subject, 'regions': Region}
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    regions  = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = TutoringPost
        exclude = ["student"]

    def validate_cost(self, value):
        return validate_cost_unit(value)

    def validate(self, attrs):
        """학년에 따라 계열을 필수 검증하거나 빈 값으로 정규화합니다."""
        attrs = super().validate(attrs)
        current_grade = getattr(self.instance, "grade", "")
        current_field = getattr(self.instance, "field", "")
        grade = attrs.get("grade", current_grade)
        field = attrs.get("field", current_field)

        if requires_student_field(grade):
            if not field:
                raise serializers.ValidationError(
                    {"field": "고등학생 및 N수생은 계열을 선택해주세요."}
                )
        else:
            # 구버전 앱이 비대상 학년과 계열을 함께 보내도 잘못된 조합을 저장하지 않습니다.
            attrs["field"] = ""

        return attrs

    def update(self, instance, validated_data):
        """마감 공고를 재개할 때만 목록 기준 시각을 현재 시각으로 갱신합니다."""
        # 관리자(신고 조치) 차단 공고는 학생이 임의로 재개할 수 없다.
        if instance.admin_blocked_at is not None and validated_data.get("is_active") is True:
            raise serializers.ValidationError(
                {"is_active": "관리자에 의해 차단된 공고는 재개할 수 없습니다."}
            )
        is_reopening = (
            validated_data.get("is_active") is True and not instance.is_active
        )
        updated_post = super().update(instance, validated_data)

        if is_reopening:
            # 재개된 공고는 새 모집글처럼 최신순과 상대 시간을 다시 계산합니다.
            updated_post.created_at = timezone.now()
            updated_post.save(update_fields=["created_at"])

        return updated_post

    def to_representation(self, instance):
        # 공고 수정 응답에도 과목/지역 레이블과 기존 상세 필드를 모두 포함한다.
        return TutoringPostDetailSerializer(instance, context=self.context).data


class StudentReviewWriteSerializer(serializers.ModelSerializer):
    """학생 리뷰 생성/수정용."""
    comment = serializers.CharField(
        allow_blank=False,
        max_length=500,
        trim_whitespace=True,
    )
    resource = serializers.PrimaryKeyRelatedField(
        queryset=TutoringResource.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = StudentReview
        fields = [
            'id', 'resource', 'student', 'instructor', 'rating', 'comment',
            'created_at'
        ]
        read_only_fields = ["instructor"]

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("평점은 1에서 5 사이여야 합니다.")
        return value

    def validate(self, attrs):
        resource = attrs.get("resource") or getattr(self.instance, "resource", None)
        if resource is None:
            if self.instance is not None and self.instance.resource_id is None:
                return super().validate(attrs)
            raise serializers.ValidationError(
                {"resource": "성사 등록된 수업 리소스가 필요합니다."}
            )
        if (
            self.instance is not None
            and self.instance.resource_id is not None
            and self.instance.resource_id != resource.pk
        ):
            raise serializers.ValidationError(
                {"resource": "리뷰가 연결된 수업은 변경할 수 없습니다."}
            )
        if resource.fee_payment_status != "PAID":
            raise serializers.ValidationError(
                {"resource": "운영 확인이 완료된 수업만 리뷰할 수 있습니다."}
            )
        duplicate_reviews = StudentReview.objects.filter(resource=resource)
        if self.instance is not None:
            duplicate_reviews = duplicate_reviews.exclude(pk=self.instance.pk)
        if duplicate_reviews.exists():
            raise serializers.ValidationError(
                {"resource": "이 수업에는 이미 작성한 리뷰가 있습니다."}
            )

        request = self.context.get("request")
        if request is not None and resource.instructor.user_id != request.user.id:
            raise serializers.ValidationError(
                {"resource": "본인이 진행한 수업만 리뷰할 수 있습니다."}
            )

        student = attrs.get("student") or getattr(self.instance, "student", None)
        if student is None or student.pk != resource.student_id:
            raise serializers.ValidationError(
                {"student": "수업 리소스의 학생과 일치하지 않습니다."}
            )
        attrs["resource"] = resource
        return super().validate(attrs)

class TutoringProposalSerializer(serializers.ModelSerializer):
    """과외 제안서 통합 Serializer (CRUD 모두 사용)"""
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=3000,
    )

    class Meta:
        model = TutoringProposal
        fields = [
            'id', 'tutoring_post', 'instructor', 'message', 'created_at'
        ]
        read_only_fields = ["instructor", "created_at"]

class TutoringResourceFileSerializer(serializers.ModelSerializer):
    file = AbsoluteFileField(read_only=True)

    class Meta:
        from .models import TutoringResourceFile
        model = TutoringResourceFile
        fields = ['id', 'file', 'uploaded_at']

class TutoringResourceSerializer(M2MSyncMixin, serializers.ModelSerializer):
    """수업 리소스 통합 Serializer (CRUD 모두 사용)"""
    files = TutoringResourceFileSerializer(many=True, read_only=True)
    fee_confirmation_file = AbsoluteFileField(required=False, allow_null=True)
    subject = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    payment_bank = serializers.SerializerMethodField()
    payment_account_number = serializers.SerializerMethodField()
    expected_commission_amount = serializers.IntegerField(read_only=True)

    m2m_fields = {'subject': Subject}

    class Meta:
        from .models import TutoringResource
        model = TutoringResource
        fields = [
            'id', 'student', 'instructor', 'start_date', 'class_type', 
            'subject', 'first_month_fee',
            'fee_confirmation_file', 'is_student_confirmed', 
            'is_instructor_confirmed', 'fee_payment_status', 'files',
            'subjects', 'payment_bank', 'payment_account_number',
            'expected_commission_amount'
        ]
        read_only_fields = [
            'is_student_confirmed', 'is_instructor_confirmed',
            'fee_payment_status',
        ]

    def validate(self, attrs):
        subjects = attrs.pop('subjects', None)
        if subjects is not None:
            if 'subject' in attrs:
                raise serializers.ValidationError(
                    {'subjects': 'subject와 subjects는 동시에 보낼 수 없습니다.'}
                )
            attrs['subject'] = subjects
        if len(attrs.get('subject', [])) > 3:
            raise serializers.ValidationError(
                {'subject': '과외 성사당 과목은 최대 3개까지만 등록할 수 있습니다.'}
            )
        return super().validate(attrs)

    def validate_subject(self, value):
        if value and len(value) > 3:
            raise serializers.ValidationError("과외 성사당 과목은 최대 3개까지만 제한하여 등록할 수 있습니다.")
        return value

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['subject'] = SubjectSimpleSerializer(instance.subject.all(), many=True).data
        request = self.context.get('request')
        registration = getattr(instance, 'registration', None)
        if request and request.user.is_authenticated and registration:
            mine = next(
                (
                    submission
                    for submission in registration.submissions.all()
                    if submission.submitted_by_id == request.user.id
                ),
                None,
            )
            ret['class_type'] = (
                '단기 수업' if mine and mine.class_type == 'SHORT_TERM'
                else '장기 수업' if mine else None
            )
            ret['first_month_fee'] = mine.first_month_fee if mine else None
            ret['attribute_validation_status'] = (
                registration.attribute_validation_status
            )
            ret['contract_status'] = registration.contract_status
            if instance.student.user == request.user:
                ret['files'] = []
        return ret

    def get_payment_bank(self, obj):
        return settings.TUTORING_PAYMENT_BANK

    def get_payment_account_number(self, obj):
        return settings.TUTORING_PAYMENT_ACCOUNT_NUMBER


class TutoringResourceListSerializer(serializers.ModelSerializer):
    """수업 리소스 목록/상세 조회용 Serializer"""
    student_user_name = serializers.CharField(source='student.user.user_name', read_only=True)
    student_first_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_last_name = serializers.CharField(source='student.user.last_name', read_only=True)
    
    instructor_user_name = serializers.CharField(source='instructor.user.user_name', read_only=True)
    instructor_first_name = serializers.CharField(source='instructor.user.first_name', read_only=True)
    instructor_last_name = serializers.CharField(source='instructor.user.last_name', read_only=True)
    
    files = TutoringResourceFileSerializer(many=True, read_only=True)
    payment_bank = serializers.SerializerMethodField()
    payment_account_number = serializers.SerializerMethodField()
    expected_commission_amount = serializers.IntegerField(read_only=True)
    my_review = serializers.SerializerMethodField()
    counterpart = serializers.SerializerMethodField()

    class Meta:
        from .models import TutoringResource
        model = TutoringResource
        exclude = [
            'fee_confirmation_file'
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['subject'] = SubjectSimpleSerializer(instance.subject.all(), many=True).data
        request = self.context.get('request')
        
        if request and request.user.is_authenticated:
            # 강사가 요청한 경우 자기 자신(강사)의 이름/닉네임은 제거하고 학생 정보만 남김
            if instance.instructor.user == request.user:
                ret.pop('instructor_user_name', None)
                ret.pop('instructor_first_name', None)
                ret.pop('instructor_last_name', None)
            # 학생이 요청한 경우 자기 자신(학생)의 이름/닉네임은 제거하고 강사 정보만 남김
            elif instance.student.user == request.user:
                ret.pop('student_user_name', None)
                ret.pop('student_first_name', None)
                ret.pop('student_last_name', None)

            registration = getattr(instance, 'registration', None)
            if registration:
                mine = next(
                    (
                        submission
                        for submission in registration.submissions.all()
                        if submission.submitted_by_id == request.user.id
                    ),
                    None,
                )
                ret['class_type'] = instance.class_type or (
                    '단기 수업' if mine and mine.class_type == 'SHORT_TERM'
                    else '장기 수업' if mine else None
                )
                ret['first_month_fee'] = (
                    instance.first_month_fee
                    if instance.first_month_fee is not None
                    else mine.first_month_fee if mine else None
                )
                ret['attribute_validation_status'] = (
                    registration.attribute_validation_status
                )
                ret['contract_status'] = registration.contract_status
                if instance.student.user == request.user:
                    ret['files'] = []
                
        return ret

    def get_payment_bank(self, obj):
        return settings.TUTORING_PAYMENT_BANK

    def get_payment_account_number(self, obj):
        return settings.TUTORING_PAYMENT_ACCOUNT_NUMBER

    def get_counterpart(self, obj):
        """현재 활성 역할을 기준으로 리뷰 작성 대상 정보를 반환합니다."""
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return None

        requested_role = (
            request.headers.get('X-Classy-Role')
            or request.query_params.get('role')
        )
        is_instructor = (
            requested_role == 'instructor'
            or (
                requested_role not in ('student', 'instructor')
                and obj.instructor.user_id == request.user.id
            )
        )

        if is_instructor:
            user = obj.student.user
            registration = getattr(obj, 'registration', None)
            chat_room = getattr(registration, 'chat_room', None)
            post = getattr(chat_room, 'post', None)
            return {
                'id': obj.student_id,
                'nickname': user.user_name,
                'profile_image': get_absolute_media_url(
                    user.profile_image,
                    request,
                ),
                'gender': getattr(post, 'sex', None) or user.sex or None,
                'grade': getattr(post, 'grade', None) or None,
                'field': getattr(post, 'field', None) or None,
                'school': None,
                'department': None,
            }

        user = obj.instructor.user
        return {
            'id': obj.instructor_id,
            'nickname': user.user_name,
            'profile_image': get_absolute_media_url(
                user.profile_image,
                request,
            ),
            'gender': None,
            'grade': None,
            'field': None,
            'school': obj.instructor.university or None,
            'department': obj.instructor.department or None,
        }

    def get_my_review(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None

        if obj.student.user_id == request.user.id:
            review = InstructorReview.objects.filter(resource=obj).first()
            if review is None:
                review = InstructorReview.objects.filter(
                    resource__isnull=True,
                    student=obj.student,
                    instructor=obj.instructor,
                ).order_by('-id').first()
            if review is None:
                return None
            return {
                'id': review.pk,
                'resource': review.resource_id,
                'professionalism': review.professionalism,
                'teaching_skill': review.teaching_skill,
                'punctuality': review.punctuality,
                'comment': review.comment,
            }

        if obj.instructor.user_id == request.user.id:
            review = StudentReview.objects.filter(resource=obj).first()
            if review is None:
                review = StudentReview.objects.filter(
                    resource__isnull=True,
                    student=obj.student,
                    instructor=obj.instructor,
                ).order_by('-id').first()
            if review is None:
                return None
            return {
                'id': review.pk,
                'resource': review.resource_id,
                'rating': review.rating,
                'comment': review.comment,
            }

        return None


class StudentMyPostSerializer(serializers.ModelSerializer):
    """
    학생이 올린 본인의 공고 조회용 Serializer
    """
    days_since_upload = serializers.SerializerMethodField()
    subjects = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField() # 대표 과목 하나
    relative_time = serializers.SerializerMethodField()

    student_name = serializers.CharField(source='student.user.user_name', read_only=True)
    user_region = serializers.CharField(source='student.user.region', read_only=True)
    age = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()

    class Meta:
        model = TutoringPost
        fields = [
            'id', 'title', 'subjects', 'subject', 'view_count', 
            'days_since_upload', 'created_at', 'is_active', 'relative_time',
            'sex', 'age', 'grade', 'field', 'method', 'cost', 'schedule', 'situation', 'etc',
            'student_name', 'user_region', 'regions'
        ]

    def get_regions(self, obj):
        return [str(region) for region in obj.regions.all()]
        
    def get_days_since_upload(self, obj):
        from django.utils import timezone
        if obj.created_at:
            delta = timezone.now() - obj.created_at
            return delta.days
        return 0

    def get_subjects(self, obj):
        return [str(subject) for subject in obj.subjects.all()]

    def get_subject(self, obj):
        # 첫 번째 과목을 대표 과목으로 반환
        first_subject = obj.subjects.all().first()
        return str(first_subject) if first_subject else ""

    def get_age(self, obj):
        from django.utils import timezone
        # 1. 공고에 저장된 나이(작성 당시 나이)와 작성일이 있는지 확인
        if obj.age and obj.created_at:
            today = timezone.now().date()
            created_date = obj.created_at.date()
            
            # 공고 작성 후 경과된 연도 계산 (단순 연도 차이가 아니라 생일 개념을 적용한 만 나이 경과)
            # 여기서는 공고의 age 자체가 이미 '만 나이'라고 가정하고, 
            # 작성일로부터 1년이 지날 때마다 1세씩 더함
            years_passed = today.year - created_date.year
            if (today.month, today.day) < (created_date.month, created_date.day):
                years_passed -= 1
            
            return obj.age + max(0, years_passed)
            
        # 2. 데이터가 부족하면 저장된 값 그대로 반환
        return obj.age

    def get_relative_time(self, obj):
        from django.utils import timezone
        if not obj.created_at:
            return ""
        now = timezone.now()
        diff = now - obj.created_at
        if diff.days > 0:
            return f"{diff.days}일 전"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}시간 전"
        minutes = diff.seconds // 60
        if minutes > 0:
            return f"{minutes}분 전"
        return "방금 전"

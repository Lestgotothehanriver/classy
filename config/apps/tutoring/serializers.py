from rest_framework import serializers
from django.db.models import Avg, Count
from django.utils import timezone

from config.apps.accounts.models import Instructor, Student, Subject
from .models import (
    TutoringPost,
    InstructorInfo,
    InstructorReview,
    StudentReview,
    TutoringProposal,
    Region,
)
from config.apps.common.serializers import M2MSyncMixin, AbsoluteFileField, AbsoluteImageField
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
    sex = serializers.CharField(source='user.sex', read_only=True)
    region = serializers.CharField(source='user.region', read_only=True)
    user_name = serializers.CharField(source='user.user_name', read_only=True)
    birth_date = serializers.DateField(source='user.birth_date', read_only=True)
    profile_image = AbsoluteImageField(source='user.profile_image', read_only=True)

    class Meta:
        model = Instructor
        fields = [
            'id', 'user', 'university', 'department', 'created_at', 
            'instruction', 'student_number', 'is_tutoring', 'last_login', 
            'subjects', 'like_count', 'is_liked', 'average_rate', 
            'review_count', 'current_rank', 'sex', 'region', 
            'user_name', 'birth_date', 'profile_image'
        ]

    def get_subjects(self, obj):
        return extract_subject_numbers(obj)


class InstructorInfoSerializer(serializers.ModelSerializer):
    """
    강사의 상세 과외 정보를 직렬화합니다.
    """
    subjects = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()
    instruction = serializers.CharField(source='instructor.instruction', read_only=True)

    class Meta:
        model = InstructorInfo
        fields = [
            'id', 'instructor', 'cost', 'schedule', 'method', 
            'location', 'etc', 'subjects', 'regions', 'instruction'
        ]

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data

    def get_regions(self, obj):
        return RegionSimpleSerializer(obj.regions.all(), many=True).data


class InstructorReviewSerializer(serializers.ModelSerializer):
    """
    강사에 대한 리뷰를 직렬화합니다.
    """
    student_id = serializers.IntegerField(source="student.id", read_only=True)
    student_label = serializers.SerializerMethodField()
    subjects = serializers.SerializerMethodField()

    class Meta:
        model = InstructorReview
        fields = [
            'id', 'instructor', 'student', 'professionalism', 
            'teaching_skill', 'punctuality', 'comment', 'created_at', 
            'subjects', 'student_id', 'student_label'
        ]

    def get_student_label(self, obj):
        user = getattr(obj.student, "user", None)
        return getattr(user, "user_name", None) or "학생"

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data


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
    student_field = serializers.CharField(source='student.user.field', read_only=True)
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
    instructor_university = serializers.CharField(source="instructor.university", read_only=True)
    instructor_department = serializers.CharField(source="instructor.department", read_only=True)
    instructor_student_number = serializers.CharField(source="instructor.student_number", read_only=True)
    instructor_subjects = serializers.SerializerMethodField()

    class Meta:
        model = StudentReview
        fields = [
            'id', 'student', 'instructor', 'rating', 'comment', 'created_at', 
            'instructor_id', 'instructor_label', 'instructor_nickname', 
            'instructor_university', 'instructor_department', 
            'instructor_student_number', 'instructor_subjects'
        ]

    def get_instructor_label(self, obj):
        return str(obj.instructor)

    def get_instructor_subjects(self, obj):
        return SubjectSimpleSerializer(obj.instructor.subjects.all(), many=True).data


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


class InstructorReviewWriteSerializer(M2MSyncMixin, serializers.ModelSerializer):
    """강사 리뷰 생성/수정용. subjects: Subject.number 리스트"""
    m2m_fields = {'subjects': Subject}
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = InstructorReview
        fields = [
            'id', 'instructor', 'student', 'professionalism', 
            'teaching_skill', 'punctuality', 'comment', 'created_at', 
            'subjects'
        ]
        read_only_fields = ["student"]

    def validate_professionalism(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("전문성 점수는 0에서 5 사이여야 합니다.")
        return value

    def validate_teaching_skill(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("강의력 점수는 0에서 5 사이여야 합니다.")
        return value

    def validate_punctuality(self, value):
        if not (0 <= value <= 5):
            raise serializers.ValidationError("시간 준수 점수는 0에서 5 사이여야 합니다.")
        return value

    # create, update 메소드는 M2MSyncMixin에서 처리됨


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


class StudentReviewWriteSerializer(serializers.ModelSerializer):
    """학생 리뷰 생성/수정용."""

    class Meta:
        model = StudentReview
        fields = [
            'id', 'student', 'instructor', 'rating', 'comment', 'created_at'
        ]
        read_only_fields = ["instructor"]

class TutoringProposalSerializer(serializers.ModelSerializer):
    """과외 제안서 통합 Serializer (CRUD 모두 사용)"""
    class Meta:
        model = TutoringProposal
        fields = [
            'id', 'tutoring_post', 'instructor', 'message'
        ]
        read_only_fields = ["instructor"]

class TutoringResourceFileSerializer(serializers.ModelSerializer):
    file = AbsoluteFileField(read_only=True)

    class Meta:
        from .models import TutoringResourceFile
        model = TutoringResourceFile
        fields = ['id', 'file', 'uploaded_at']

class TutoringResourceSerializer(serializers.ModelSerializer):
    """수업 리소스 통합 Serializer (CRUD 모두 사용)"""
    files = TutoringResourceFileSerializer(many=True, read_only=True)
    fee_confirmation_file = AbsoluteFileField(required=False, allow_null=True)

    class Meta:
        from .models import TutoringResource
        model = TutoringResource
        fields = [
            'id', 'student', 'instructor', 'start_date', 'class_type', 
            'subject', 'first_month_fee', 'payback_bank', 
            'payback_account_number', 'payback_account_holder', 
            'fee_confirmation_file', 'is_student_confirmed', 
            'is_instructor_confirmed', 'fee_payment_status', 'files'
        ]


class TutoringResourceListSerializer(serializers.ModelSerializer):
    """수업 리소스 목록/상세 조회용 Serializer"""
    student_user_name = serializers.CharField(source='student.user.user_name', read_only=True)
    student_first_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_last_name = serializers.CharField(source='student.user.last_name', read_only=True)
    
    instructor_user_name = serializers.CharField(source='instructor.user.user_name', read_only=True)
    instructor_first_name = serializers.CharField(source='instructor.user.first_name', read_only=True)
    instructor_last_name = serializers.CharField(source='instructor.user.last_name', read_only=True)
    
    files = TutoringResourceFileSerializer(many=True, read_only=True)

    class Meta:
        from .models import TutoringResource
        model = TutoringResource
        exclude = [
            'payback_bank',
            'payback_account_number',
            'payback_account_holder',
            'fee_confirmation_file'
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
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
                
        return ret

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

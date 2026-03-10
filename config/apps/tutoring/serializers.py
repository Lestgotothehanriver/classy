from rest_framework import serializers
from django.db.models import Avg, Count

from config.apps.accounts.models import Instructor, Student, Subject
from .models import (
    TutoringPost,
    InstructorInfo,
    InstructorReview,
    StudentReview,
    Region,
    TutoringProposal,
)


# ____________________________________________________________________________________
# 공통 유틸: "민감할 수 있는 필드" 제거용 Serializer
# ____________________________________________________________________________________
class SafeModelSerializer(serializers.ModelSerializer):
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


# ____________________________________________________________________________________
# 공통 유틸: Subject를 "id + label(str)"로만 가볍게 표현
# ____________________________________________________________________________________
class SubjectSimpleSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ["id", "label"]

    def get_label(self, obj):
        return str(obj)


# ____________________________________________________________________________________
# 공통 유틸: Region을 "id + label(str)"로만 가볍게 표현
# ____________________________________________________________________________________
class RegionSimpleSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = Region
        fields = ["id", "label"]

    def get_label(self, obj):
        return str(obj)


# ____________________________________________________________________________________
# 공통 유틸: Student/Instructor의 subjects M2M 필드에서 id 리스트 반환
# ____________________________________________________________________________________
def extract_subject_ids(owner_obj):
    """Student/Instructor의 subjects M2M 필드에서 Subject id 목록을 반환."""
    if hasattr(owner_obj, 'subjects'):
        return list(owner_obj.subjects.values_list("id", flat=True))
    return []


# ____________________________________________________________________________________
# 학생 페이지: 강사 리스트/세부에 쓰는 Serializer
# ____________________________________________________________________________________
class InstructorListSerializer(SafeModelSerializer):
    subject_ids = serializers.SerializerMethodField()
    like_count = serializers.IntegerField(read_only=True, default=0)
    sex = serializers.CharField(source='user.sex', read_only=True)
    region = serializers.CharField(source='user.region', read_only=True)
    user_name = serializers.CharField(source='user.user_name', read_only=True)

    class Meta:
        model = Instructor
        exclude = ["instruction"]

    def get_subject_ids(self, obj):
        return extract_subject_ids(obj)




# ____________________________________________________________________________________
# 학생 페이지: 강사 과외정보(InstructorInfo)
# ____________________________________________________________________________________
class InstructorInfoSerializer(serializers.ModelSerializer):
    subjects = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()
    instruction = serializers.CharField(source='instructor.instruction', read_only=True)

    class Meta:
        model = InstructorInfo
        fields = "__all__"

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data

    def get_regions(self, obj):
        return RegionSimpleSerializer(obj.regions.all(), many=True).data


# ____________________________________________________________________________________
# 학생 페이지: 강사 리뷰(InstructorReview)
# ____________________________________________________________________________________
class InstructorReviewSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source="student.id", read_only=True)
    student_label = serializers.SerializerMethodField()
    subjects = serializers.SerializerMethodField()

    class Meta:
        model = InstructorReview
        fields = "__all__"

    def get_student_label(self, obj):
        return str(obj.student)

    def get_subjects(self, obj):
        return SubjectSimpleSerializer(obj.subjects.all(), many=True).data


# ____________________________________________________________________________________
# 강사 페이지: 공고 리스트/세부 (TutoringPost)
# ____________________________________________________________________________________
class StudentPublicSerializer(SafeModelSerializer):
    subject_ids = serializers.SerializerMethodField()
    avg_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Student
        fields = "__all__"

    def get_subject_ids(self, obj):
        return extract_subject_ids(obj)


class TutoringPostListSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='student.user.first_name', read_only=True)
    last_name = serializers.CharField(source='student.user.last_name', read_only=True)
    user_name = serializers.CharField(source='student.user.user_name', read_only=True)
    birth_date = serializers.DateField(source='student.user.birth_date', read_only=True)
    subjects = serializers.SerializerMethodField()
    regions = serializers.SerializerMethodField()

    class Meta:
        model = TutoringPost
        fields = [
            'id',
            'first_name',
            'last_name',
            'user_name',
            'birth_date',
            'sex',
            'grade',
            'regions',
            'subjects'
        ]

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
        fields = "__all__"

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

    class Meta:
        model = StudentReview
        fields = "__all__"

    def get_instructor_label(self, obj):
        return str(obj.instructor)


# ____________________________________________________________________________________
# Write Serializers — Create / Patch 용 (subjects/regions는 number 리스트로 받아 M2M set)
# ____________________________________________________________________________________

def _sync_m2m(manager, model_cls, numbers):
    """number 리스트 → 객체 리스트로 변환 후 M2M set."""
    objs = [model_cls.objects.get_or_create(number=n)[0] for n in numbers]
    manager.set(objs)


class InstructorInfoWriteSerializer(serializers.ModelSerializer):
    """
    강사 과외정보 생성/수정용.
    subjects: Subject.number 리스트, regions: Region.number 리스트
    """
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    regions  = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = InstructorInfo
        exclude = ["instructor"]

    def create(self, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        regions_data = validated_data.pop("regions", None)
        instance = super().create(validated_data)
        from config.apps.accounts.models import Subject
        if subjects_data is not None:
            _sync_m2m(instance.subjects, Subject, subjects_data)
        if regions_data is not None:
            _sync_m2m(instance.regions, Region, regions_data)
        return instance

    def update(self, instance, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        regions_data = validated_data.pop("regions", None)
        instance = super().update(instance, validated_data)
        from config.apps.accounts.models import Subject
        if subjects_data is not None:
            _sync_m2m(instance.subjects, Subject, subjects_data)
        if regions_data is not None:
            _sync_m2m(instance.regions, Region, regions_data)
        return instance


class InstructorReviewWriteSerializer(serializers.ModelSerializer):
    """강사 리뷰 생성/수정용. subjects: Subject.number 리스트"""
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = InstructorReview
        fields = "__all__"
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

    def create(self, validated_data):
        from config.apps.accounts.models import Subject
        nums = validated_data.pop("subjects", None)
        instance = InstructorReview.objects.create(**validated_data)
        if nums is not None:
            _sync_m2m(instance.subjects, Subject, nums)
        return instance

    def update(self, instance, validated_data):
        from config.apps.accounts.models import Subject
        nums = validated_data.pop("subjects", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if nums is not None:
            _sync_m2m(instance.subjects, Subject, nums)
        return instance


class TutoringPostWriteSerializer(serializers.ModelSerializer):
    """
    과외 공고 생성/수정용.
    subjects: Subject.number 리스트, regions: Region.number 리스트
    """
    subjects = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    regions  = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)

    class Meta:
        model = TutoringPost
        exclude = ["student"]

    def create(self, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        regions_data = validated_data.pop("regions", None)
        instance = super().create(validated_data)
        from config.apps.accounts.models import Subject
        if subjects_data is not None:
            _sync_m2m(instance.subjects, Subject, subjects_data)
        if regions_data is not None:
            _sync_m2m(instance.regions, Region, regions_data)
        return instance

    def update(self, instance, validated_data):
        subjects_data = validated_data.pop("subjects", None)
        regions_data = validated_data.pop("regions", None)
        instance = super().update(instance, validated_data)
        from config.apps.accounts.models import Subject
        if subjects_data is not None:
            _sync_m2m(instance.subjects, Subject, subjects_data)
        if regions_data is not None:
            _sync_m2m(instance.regions, Region, regions_data)
        return instance


class StudentReviewWriteSerializer(serializers.ModelSerializer):
    """학생 리뷰 생성/수정용."""

    class Meta:
        model = StudentReview
        fields = "__all__"
        read_only_fields = ["instructor"]

class TutoringProposalSerializer(serializers.ModelSerializer):
    """과외 제안서 통합 Serializer (CRUD 모두 사용)"""
    class Meta:
        model = TutoringProposal
        fields = "__all__"
        read_only_fields = ["instructor"]

class TutoringResourceSerializer(serializers.ModelSerializer):
    """수업 리소스 통합 Serializer (CRUD 모두 사용)"""
    class Meta:
        from .models import TutoringResource
        model = TutoringResource
        fields = "__all__"


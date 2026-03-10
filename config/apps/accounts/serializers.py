# config/apps/accounts/serializers.py

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Student, Instructor, Subject
from config.apps.pending.models import PendingInstructor, File


User = get_user_model()


class StudentSignupSerializer(serializers.Serializer):
    """
    학생 회원가입:
    - User 생성 + StudentProfile 생성
    - studentsubject(수강/관심 과목) 저장 지원

    요청 데이터 예시 (application/json):
    {
    "email": "student@example.com",
    "password": "securepassword",
    "first_name": "John",
    "last_name": "Doe",
    "user_name": "johnny",
    "phone": "01012345678",
    "sex": "남성",
    "birth_date": "2000-01-01",
    "region": "울산 남구",
    "studentsubject": [1, 3, 5]
    }
    """
    sex = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    user_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    region = serializers.CharField(required=False, allow_blank=True)

    # (기존 호환) 관심사 문자열 리스트. 사용 안 해도 됨.
    interests = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        write_only=True,
    )

    # Subject id 리스트 (ex: [1,2,3])
    studentsubject = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
        write_only=True,
    )

    birth_date = serializers.DateField(required=False, allow_null=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    @transaction.atomic
    def create(self, validated_data):
        studentsubject_ids = validated_data.pop("studentsubject", []) or []
        validated_data.pop("interests", None)

        email = validated_data["email"].lower()
        password = validated_data["password"]
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")

        # AbstractUser 기본 username이 필요할 가능성이 높아서 안전하게 만들어줌
        username = email

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            sex=validated_data.get("sex", ""),
        )
        user.user_name = validated_data.get("user_name", "")
        user.phone = validated_data.get("phone", "")
        region = validated_data.get("region", "")
        user.birth_date = validated_data.get("birth_date", None)

        # update_fields에 누락되면 저장 안 되는 버그 방지
        user.save(update_fields=["user_name", "phone", "region", "birth_date"])

        student_profile = Student.objects.create(user=user)

        # 학생 과목 저장 (M2M)
        if studentsubject_ids:
            subjects = []
            for num in studentsubject_ids:
                obj, _ = Subject.objects.get_or_create(number=num)
                subjects.append(obj)
            student_profile.subjects.set(subjects)
        return user


class InstructorSignupSerializer(serializers.Serializer):
    """
    강사 회원가입:
    - User 생성 + InstructorProfile 생성
    - PendingInstructor 생성(status=PENDING)
    - instructorsubject(강의 가능 과목) 저장 지원

    요청 데이터 예시 (multipart/form-data):
    {
        "email": "instructor@example.com",
        "password": "securepassword",
        "first_name": "Jane",
        "last_name": "Smith",
        "user_name": "jane",
        "phone": "01000000000",
        "sex": "여성",
        "birth_date": "1998-03-02",
        "region": "울산 남구",
        "university": "울산대학교",
        "department": "컴퓨터공학과",
        "instruction": "자기소개...",
        "student_number": "2018",
        "instructorsubject": [2, 4],   // Subject id 리스트 (프론트에서 JSON string으로 보내도 됨)
        "pending_file": <파일>
    }

    * multipart에서 instructorsubject를 JSON string으로 보내는 경우 예:
      instructorsubject: "[2,4]"
      -> 프론트에서 가능하면 배열로 보내고, 불가하면 문자열로 보내도 아래에서 파싱 처리함
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    user_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    sex = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    region = serializers.CharField(required=False, allow_blank=True)

    # InstructorProfile 필드
    university = serializers.CharField()
    department = serializers.CharField(required=False, allow_blank=True)
    instruction = serializers.CharField(required=False, allow_blank=True)
    student_number = serializers.CharField(required=False, allow_blank=True)

    # Subject id 리스트
    instructorsubject = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
        write_only=True,
    )

    # PendingInstructor 필드 (FileField는 request.FILES로 들어옴)
    pending_file = serializers.FileField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        """
        multipart/form-data에서 배열이 문자열로 들어오는 케이스를 최소 수정으로 흡수.
        - instructorsubject: "[1,2]" 처럼 들어오면 list로 파싱 시도.
        """
        ret = super().to_internal_value(data)
        raw = data.get("instructorsubject", None)
        if isinstance(raw, str):
            raw = raw.strip()
            if raw.startswith("[") and raw.endswith("]"):
                import json
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        ret["instructorsubject"] = parsed
                except Exception:
                    # 파싱 실패하면 기본 validation에서 잡히게 둠
                    pass
        return ret

    @transaction.atomic
    def create(self, validated_data):
        instructorsubject_ids = validated_data.pop("instructorsubject", []) or []

        email = validated_data["email"].lower()
        password = validated_data["password"]
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")
        username = email

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
        )
        user.user_name = validated_data.get("user_name", "")
        user.phone = validated_data.get("phone", "")
        user.sex = validated_data.get("sex", "")
        user.birth_date = validated_data.get("birth_date", None)
        user.region = validated_data.get("region", "")

        user.save(update_fields=["user_name", "phone", "sex", "birth_date", "region"])

        instructor_profile = Instructor.objects.create(
            user=user,
            university=validated_data["university"],
            department=validated_data.get("department", ""),
            instruction=validated_data.get("instruction", ""),
            student_number=validated_data.get("student_number", ""),
        )

        PendingInstructor.objects.create(
            instructor_profile=instructor_profile,
            status=PendingInstructor.Status.PENDING,
        )

        file = validated_data["pending_file"]
        pending_instructor = instructor_profile.pending_info
        File.objects.create(pending_instructor=pending_instructor, pending_file=file)

        # 강사 과목 저장 (M2M)
        if instructorsubject_ids:
            subjects = []
            for num in instructorsubject_ids:
                obj, _ = Subject.objects.get_or_create(number=num)
                subjects.append(obj)
            instructor_profile.subjects.set(subjects)
        return user


class StudentUpdateSerializer(serializers.Serializer):
    """
    학생 프로필 수정 (PUT/PATCH 용도)
    - 인증된 사용자(request.user)를 instance로 받는다.

    요청 데이터 예시 (application/json):
    {
        "user_name": "new_nickname",
        "region": "부산 해운대구",
        "first_name": "John",
        "last_name": "Doe",
        "phone": "01099998888"
    }
    """

    user_name = serializers.CharField(required=False, allow_blank=True)
    region = serializers.CharField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    @transaction.atomic
    def update(self, instance, validated_data):
        # instance = request.user
        for field in ["user_name", "region", "first_name", "last_name", "phone"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.save()

        return instance


class InstructorUpdateSerializer(serializers.Serializer):
    """
    강사 프로필 수정 (PUT/PATCH 용도)
    - 인증된 사용자(request.user)를 instance로 받는다.
    - instructorsubject를 같이 보내면, 기존 과목을 전부 교체(replace)한다.

    요청 데이터 예시 (multipart/form-data 또는 application/json):
    {
        "sex": "여성",
        "birth_date": "1998-03-02",
        "region": "울산 남구",
        "instruction": "자기소개 수정",
        "instructorsubject": [2, 4]   // 배열 or "[2,4]" 문자열 (보내면 전체 교체)
    }
    """

    sex = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    region = serializers.CharField(required=False, allow_blank=True)

    instruction = serializers.CharField(required=False, allow_blank=True)
    is_tutoring = serializers.BooleanField(required=False)

    instructorsubject = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
    )

    def _coerce_subject_ids(self, raw):
        # multipart/form-data에서 "[1,2]" 형태로 오는 케이스 방어
        if raw is None:
            return None
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            import json
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return raw

    @transaction.atomic
    def update(self, instance, validated_data):
        # instance = request.user
        raw_subject_ids = validated_data.pop("instructorsubject", None)
        subject_ids = self._coerce_subject_ids(raw_subject_ids)

        for field in ["sex", "birth_date", "region"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.save()

        if not hasattr(instance, "instructor_profile"):
            # 강사 전용 필드가 없으면 여기서 종료
            if subject_ids is not None:
                raise serializers.ValidationError({"detail": "강사 프로필이 없습니다."})
            return instance

        instructor = instance.instructor_profile

        for field in ["instruction", "is_tutoring"]:
            if field in validated_data:
                setattr(instructor, field, validated_data[field])
        instructor.save()

        if subject_ids is not None:
            subjects = []
            for num in subject_ids:
                obj, _ = Subject.objects.get_or_create(number=num)
                subjects.append(obj)
            instructor.subjects.set(subjects)
        return instance

# config/apps/accounts/serializers.py

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .models import Student, Instructor, Subject
from config.apps.pending.models import PendingInstructor, File
from config.apps.notification.models import DeviceToken


User = get_user_model()


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'number', 'name']


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
            user_name=validated_data.get("user_name", ""),  # UNIQUE 제약 오류 방지
        )
        user.phone = validated_data.get("phone", "")
        user.region = validated_data.get("region", "")
        user.birth_date = validated_data.get("birth_date", None)

        user.save(update_fields=["phone", "region", "birth_date"])

        student_profile = Student.objects.create(user=user)

        # 학생 과목 저장 (M2M)
        if studentsubject_ids:
            subjects = []
            for num in studentsubject_ids:
                obj, _ = Subject.objects.get_or_create(number=num)
                subjects.append(obj)
            student_profile.subjects.set(subjects)
        return user
    # 닉네임 중복 체크 함수
    def is_validate_user_name(self, user_name):
        return not User.objects.filter(user_name__iexact=user_name).exists() # 대소문자 구분 없이 체크


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
    # multipart/form-data에서 JSON 문자열로 수신: "[196, 197]"
    instructorsubject = serializers.CharField(
        required=False,
        allow_blank=True,
        default='[]',
        write_only=True,
    )

    # pending_file은 마이페이지로 이전됨
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    # FCM 디바이스 토큰 (회원가입 직후 DeviceToken 등록용)
    fcm_token = serializers.CharField(required=False, allow_blank=True, write_only=True)
    platform = serializers.CharField(required=False, allow_blank=True, write_only=True, default='android')

    @transaction.atomic
    def create(self, validated_data):
        import json
        # CharField로 받은 instructorsubject를 List[int]로 파싱
        raw = validated_data.pop("instructorsubject", "[]") or "[]"
        if isinstance(raw, list):
            instructorsubject_ids = [int(x) for x in raw]
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                instructorsubject_ids = [int(x) for x in parsed if str(x).strip().lstrip('-').isdigit()]
            except Exception:
                instructorsubject_ids = []
        else:
            instructorsubject_ids = []
        
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
            user_name=validated_data.get("user_name", ""),  # UNIQUE 제약 오류 방지
        )
        user.phone = validated_data.get("phone", "")
        user.sex = validated_data.get("sex", "")
        user.birth_date = validated_data.get("birth_date", None)
        user.region = validated_data.get("region", "")

        user.save(update_fields=["phone", "sex", "birth_date", "region"])

        instructor_profile = Instructor.objects.create(
            user=user,
            university=validated_data["university"],
            department=validated_data.get("department", ""),
            instruction=validated_data.get("instruction", ""),
            student_number=validated_data.get("student_number", ""),
        )

        # 회원가입 단계에서는 PendingInstructor를 자동으로 생성하지 않습니다.
        # PendingInstructor.objects.create(
        #     instructor_profile=instructor_profile,
        #     status=PendingInstructor.Status.PENDING,
        # )



        # 강사 과목 저장 (M2M)
        if instructorsubject_ids:
            subjects = []
            for num in instructorsubject_ids:
                obj, _ = Subject.objects.get_or_create(number=int(num) if isinstance(num, str) else num)
                subjects.append(obj)
            instructor_profile.subjects.set(subjects)

        # FCM 디바이스 토큰 등록 (회원가입 시점에 등록 — PENDING 상태라 로그인 불가하므로)
        # 실무 표준: 하나의 기기(토큰) = 하나의 활성 유저
        # 같은 토큰이 다른 유저에게 등록돼 있으면 먼저 해제하고 현재 유저에게 할당
        fcm_token = validated_data.get('fcm_token', '').strip()
        platform = validated_data.get('platform', 'android')
        if fcm_token:
            # 다른 유저가 동일 토큰을 가지고 있으면 제거 (이 기기를 현재 유저가 사용 중)
            DeviceToken.objects.filter(token=fcm_token).exclude(user=user).delete()
            DeviceToken.objects.get_or_create(
                token=fcm_token,
                defaults={'user': user, 'platform': platform, 'is_active': True},
            )

        return user
    
    # 닉네임 중복 체크 함수
    def is_validate_user_name(self, user_name):
        return not User.objects.filter(user_name__iexact=user_name).exists() # 대소문자 구분 없이 체크


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
    field = serializers.CharField(required=False, allow_blank=True)  # 문과/이과/예체능/기타

    @transaction.atomic
    def update(self, instance, validated_data):
        # instance = request.user
        for field in ["user_name", "region", "first_name", "last_name", "phone", "field"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.save()
        return instance
    
    # 닉네임 업데이트 시 중복 체크 함수 (본인 제외) 반환: true(available), false(unavailable)
    def is_validate_user_name(self, user_name):
        # 현재 사용자의 닉네임은 유효하다고 간주
        queryset = User.objects.filter(user_name__iexact=user_name) # 일단 같은 닉네임이 있는지 체크

        # 만약 업데이트 중인 닉네임이 본인 것이라면, 중복 체크에서 제외해야 함
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk) # 본인 제외
        return not queryset.exists()


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
    
    # 닉네임 업데이트 시 중복 체크 함수 (본인 제외) 반환: true(available), false(unavailable)
    def is_validate_user_name(self, user_name):
        # 현재 사용자의 닉네임은 유효하다고 간주
        queryset = User.objects.filter(user_name__iexact=user_name) # 일단 같은 닉네임이 있는지 체크

        # 만약 업데이트 중인 닉네임이 본인 것이라면, 중복 체크에서 제외해야 함
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk) # 본인 제외
        return not queryset.exists()

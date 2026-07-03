# accounts/models.py
# "학생/강사"를 나누는 데 **진짜 꼭 필요한 최소 모델**만 남긴 예시.
# 핵심 아이디어:
# 1) User는 로그인/공통 정보만 가진다.
# 2) 학생/강사 전용 정보는 각각 Profile로 분리한다. (1:1)
# 3) 한 사람이 학생+강사 둘 다 될 수 있게, 두 프로필을 동시에 가질 수도 있다.
#
# (Role 테이블까지 만들면 더 유연해지지만, "최소" 버전에서는 생략)

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from config.apps.tutoring.constant import STUDENT_SUBJECT_CHOICES

sex_choices = [
    ("남성", "남성"),
    ("여성", "여성"),
    ("기타", "기타"),
]

field_choices = [
    ("문과", "문과"),
    ("이과", "이과"),
    ("예체능", "예체능"),
    ("기타", "기타"),
]

class Subject(models.Model):
    """
    플랫폼에서 지원하는 모든 과목(Subject)의 마스터 데이터를 관리하는 모델입니다.
    
    학생과 강사 모두 다대다(M:N) 관계로 참조하며, STUDENT_SUBJECT_CHOICES에 정의된
    상수(number)를 기준으로 이름(name)을 동기화합니다.
    
    Attributes:
        number (int): 과목 고유 식별 번호 (STUDENT_SUBJECT_CHOICES 참조).
        name (str): 과목명 (저장 시 number 기반으로 자동 생성/매핑됨).
    """
    number = models.IntegerField(choices=STUDENT_SUBJECT_CHOICES, unique=True)
    name = models.CharField(max_length=100, blank=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = dict(STUDENT_SUBJECT_CHOICES).get(self.number, '')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or dict(STUDENT_SUBJECT_CHOICES).get(self.number, str(self.number))

class User(AbstractUser):
    """공통 사용자 모델입니다.
    
    Attributes:
        phone (str): 고유 식별을 위한 전화번호.
        email (str): 로그인 및 연락용 이메일.
        user_name (str): 사용자 닉네임.
        sex (str): 성별.
        birth_date (date): 생년월일.
        region (str): 거주 지역.
        field (str): 계열(문과/이과 등).
        cash (int): 보유 캐시 잔액.
        profile_image (ImageField): 프로필 이미지.
        is_banned (bool): 서비스 정지 여부.
        withdraw_reason (str): 탈퇴 사유 요약.
        withdraw_reason_detail (str): 탈퇴 상세 사유.
    """
    phone = models.CharField(max_length=20, unique=True, blank=True, null=True)
    email = models.EmailField()
    password = models.CharField(max_length=128)
    user_name = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    sex = models.CharField(max_length=10, choices=sex_choices, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    region = models.CharField(max_length=50, blank=True)
    field = models.CharField(max_length=10, choices=field_choices, blank=True)
    cash = models.PositiveIntegerField(default=0)
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    is_banned = models.BooleanField(default=False)
    withdraw_reason = models.CharField(max_length=255, blank=True)
    withdraw_reason_detail = models.TextField(blank=True)  # 탈퇴 상세 사유



class Student(models.Model):
    """
    학생 전용 프로필 모델입니다.
    
    User 모델과 1:1 관계로 연결되어 있으며, 과외를 구하거나 강의를 수강하는
    '학생' 역할에 특화된 데이터만을 분리하여 저장합니다. 
    한 사용자가 강사이면서 동시에 학생일 수 있도록 설계되었습니다.
    
    Attributes:
        user (OneToOneField): 공통 User 모델과의 1:1 연결. (related_name="student_profile")
        subjects (ManyToManyField): 학생이 수강을 희망하거나 관심 있는 과목 목록.
        last_login (DateTimeField): 학생 프로필로 서비스에 마지막으로 접속한 일시.
        created_at (DateTimeField): 학생 프로필 생성 일시.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
        # related_name 덕분에 user.student_profile 로 접근 가능
    )
    subjects = models.ManyToManyField('Subject', blank=True, related_name='students')
    last_login = models.DateTimeField(null=True, blank=True)  # 학생 계정 마지막 로그인
    created_at = models.DateTimeField(auto_now_add=True)


class Instructor(models.Model):
    """
    강사 전용 프로필 모델입니다.
    
    User 모델과 1:1 관계로 연결되어 있으며, 강의 업로드, 과외 프로필 노출,
    학교 인증 등 '강사' 역할에 필요한 데이터를 관리합니다.
    
    Attributes:
        user (OneToOneField): 공통 User 모델과의 1:1 연결. (related_name="instructor_profile")
        subjects (ManyToManyField): 강사가 강의 및 과외 가능한 과목 목록.
        university (str): 재학/졸업 대학교명 (학교 인증 시 필수).
        department (str): 소속 학과명.
        instruction (str): 강사 자기소개 또는 대표 슬로건.
        student_number (str): 대학교 학번 (학교 인증 및 검증용).
        is_tutoring (bool): 현재 과외 진행 중인지 여부.
        last_login (DateTimeField): 강사 프로필로 서비스에 마지막으로 접속한 일시.
        created_at (DateTimeField): 강사 프로필 생성 일시.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="instructor_profile",
    )
    subjects = models.ManyToManyField('Subject', blank=True, related_name='instructors')

    # 학교 인증에 필요한 최소 정보 (너희 서비스 핵심이 "학교 인증"이니까)
    university = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    instruction = models.TextField(blank=True, default="")  # 자기소개 같은 용도로 쓰는 필드
    student_number = models.CharField(max_length=20, blank=True)  # 학번 (인증에 필요하면 추가)
    is_tutoring = models.BooleanField(default=False)  # 과외 진행 중 여부
    last_login = models.DateTimeField(null=True, blank=True)  # 강사 계정 마지막 로그인
     

class InstructorLike(models.Model):
    """
    학생이 강사 프로필을 '좋아요(찜)'한 내역을 관리하는 모델입니다.
    
    학생(Student)과 강사(Instructor) 간의 M:N 관계를 해소하는 중간 테이블(Through Model)
    역할을 수행하며, 찜한 날짜 기록을 위해 명시적으로 분리되었습니다.
    
    Attributes:
        student (ForeignKey): 좋아요를 누른 학생.
        instructor (ForeignKey): 좋아요를 받은 강사.
        created_at (DateTimeField): 좋아요를 누른 일시.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='likes')
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='liked_by')
    created_at = models.DateTimeField(auto_now_add=True)

class StudentLike(models.Model):
    """
    강사가 학생 프로필(또는 과외 구인 공고와 연관된 학생)을 '좋아요(관심등록)'한 내역을 관리하는 모델입니다.
    
    강사(Instructor)와 학생(Student) 간의 M:N 관계를 해소하는 중간 테이블(Through Model)입니다.
    
    Attributes:
        instructor (ForeignKey): 관심 등록을 한 강사.
        student (ForeignKey): 관심 등록 대상이 된 학생.
        created_at (DateTimeField): 관심 등록 일시.
    """
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='likes')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='liked_by')
    created_at = models.DateTimeField(auto_now_add=True)


class PhoneVerification(models.Model):
    """
    전화번호 인증(OTP) 내역 및 인증 상태를 관리하는 모델입니다.
    
    회원가입, 비밀번호 찾기, 휴대전화 번호 변경 시 SMS로 발송된
    인증 번호(code)와 확인 여부(is_verified)를 기록합니다.
    
    Attributes:
        user (ForeignKey): 인증을 요청한 사용자.
        phone (str): 인증 대상 전화번호.
        code (str): 발송된 인증 코드 (예: 6자리 숫자).
        is_verified (bool): 사용자가 올바른 코드를 입력하여 인증을 완료했는지 여부.
        created_at (DateTimeField): 인증 코드 발송 일시.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="phone_verifications")
    phone = models.CharField(max_length=20)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
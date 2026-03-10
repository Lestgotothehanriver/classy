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

class Subject(models.Model):
    number = models.IntegerField(choices=STUDENT_SUBJECT_CHOICES, unique=True)

    def __str__(self):
        return dict(STUDENT_SUBJECT_CHOICES).get(self.number, str(self.number))

class User(AbstractUser):
    """
    공통 사용자 모델.
    - 로그인/인증은 Django 기본(AbstractUser)을 그대로 사용
    - username/password/email 등 기본 필드를 이미 제공함
    - 우리는 추가로 공통 프로필만 여기 넣는다 (ex: phone)
    """
    #_____________________________________________
    # 로그인 및 인증에 필요한 정보
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField()  # 이메일로 로그인할 거면 unique=True
    password = models.CharField(max_length=128)  # Django 기본 필드 유지
    user_name = models.CharField(max_length=150, blank=True)  # 닉네임 같은 용도로 쓰는 필드
    first_name = models.CharField(max_length=30, blank=True)  # Django 기본 필드 유지
    last_name = models.CharField(max_length=150, blank=True)  # Django 기본 필드 유지
    #_____________________________________________
    # 가입 시 받는 정보들
    sex = models.CharField(max_length=10, choices = sex_choices, blank=True)
    birth_date = models.DateField(null=True, blank=True)  # 생년월일  
    region = models.CharField(max_length=50, blank=True)  
    cash = models.PositiveIntegerField(default=0)  # 캐시 잔액


class Student(models.Model):
    """
    학생 전용 데이터.
    - User와 1:1 관계 (한 유저는 학생 프로필을 0개 또는 1개 가짐)
    - 학생 기능(공고 작성, 과외 선생님 찾기 등)에 필요한 데이터만 여기 둔다.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
        # related_name 덕분에 user.student_profile 로 접근 가능
    )
    subjects = models.ManyToManyField('Subject', blank=True, related_name='students')

    created_at = models.DateTimeField(auto_now_add=True)


class Instructor(models.Model):
    """
    강사 전용 데이터.
    - User와 1:1 관계
    - 강사 기능(강의 업로드, 과외 정보 노출, 학교 인증 상태)에 필요한 데이터만 여기 둔다.
    """

    # 강사 인증/활동 상태 (최소로 2~3개만 두는 게 관리하기 편함)
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="instructor_profile",
        # user.instructor_profile 로 접근 가능
    )
    subjects = models.ManyToManyField('Subject', blank=True, related_name='instructors')

    # 학교 인증에 필요한 최소 정보 (너희 서비스 핵심이 "학교 인증"이니까)
    university = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    instruction = models.TextField(blank=True, default="")  # 자기소개 같은 용도로 쓰는 필드
    student_number = models.CharField(max_length=20, blank=True)  # 학번 (인증에 필요하면 추가)
    is_tutoring = models.BooleanField(default=False)  # 과외 진행 중 여부
    

class InstructorLike(models.Model):
    """
    학생이 강사를 좋아요하는 모델.
    - 학생과 강사 모두 1:N 관계 (한 학생은 여러 강사를 좋아할 수 있고, 한 강사는 여러 학생에게 좋아요 받을 수 있음)
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='likes')
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='liked_by')
    created_at = models.DateTimeField(auto_now_add=True)

class StudentLike(models.Model):
    """
    강사가 학생을 좋아요하는 모델.
    - 강사와 학생 모두 1:N 관계 (한 강사는 여러 학생을 좋아할 수 있고, 한 학생은 여러 강사에게 좋아요 받을 수 있음)
    """
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='likes')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='liked_by')
    created_at = models.DateTimeField(auto_now_add=True)
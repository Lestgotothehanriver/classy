from django.db import models
from config.apps.accounts.models import Instructor, Student, Subject
from config.apps.tutoring.constant import REGION_CHOICES, STUDENT_SUBJECT_CHOICES

#____________________________________________________________________________________________________


class Region(models.Model):
    number = models.IntegerField(choices=REGION_CHOICES, unique=True)

    def __str__(self):
        return dict(REGION_CHOICES).get(self.number, str(self.number))

#____________________________________________________________________________________________________

student_sex_choices = [
    ("남성", "남성"),
    ("여성", "여성"),
]
student_field_choices = [
    ("문과", "문과"),
    ("이과", "이과"),
    ("예체능", "예체능"),
    ("기타", "기타"),
]

method_choices = [
    ("대면", "대면"),
    ("비대면", "비대면"),
]

grade_choices = [
    ("유치원생", "유치원생"),
    ("초1", "초1")  ,
    ("초2", "초2"),
    ("초3", "초3"),
    ("초4", "초4"),
    ("초5", "초5"),
    ("초6", "초6"),
    ("중1", "중1"),
    ("중2", "중2"),
    ("중3", "중3"),
    ("고1", "고1"),
    ("고2", "고2"),
    ("고3", "고3"),
    ("재수생", "재수생"),
    ("사회인", "사회인"),
]
#____________________________________________________________________________________________________

class TutoringPost(models.Model):
    # 모집 공고 모델
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="tutoring_posts")
    sex = models.CharField(max_length=10, choices=student_sex_choices, blank=True)
    age = models.IntegerField(blank=True, null=True)
    grade = models.CharField(max_length=20, choices=grade_choices, blank=True)
    field = models.CharField(max_length=20, choices=student_field_choices, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='tutoring_posts')
    method = models.CharField(max_length=20, choices=method_choices, blank=True)
    regions = models.ManyToManyField(Region, blank=True, related_name='tutoring_posts')
    cost = models.IntegerField(blank=True, null=True)
    schedule = models.CharField(max_length=255, blank=True)
    situation = models.CharField(max_length=255, blank=True)
    etc = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

class TutoringPostLike(models.Model):
    """
    강사가 과외 공고를 좋아요하는 모델.
    - 강사와 공고 모두 1:N 관계
    """
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='post_likes')
    tutoring_post = models.ForeignKey(TutoringPost, on_delete=models.CASCADE, related_name='liked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('instructor', 'tutoring_post')

class TutoringProposal(models.Model):
    # 과외 제안서 모델
    tutoring_post = models.ForeignKey(TutoringPost, on_delete=models.CASCADE, related_name="proposal")
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="proposals")
    message = models.TextField(blank=True)

class InstructorInfo(models.Model):
    instructor = models.OneToOneField(Instructor, on_delete=models.CASCADE, related_name="tutoring_profile")
    cost = models.IntegerField(blank=True, null=True)
    schedule = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=255, blank=True, choices=method_choices)
    location = models.CharField(max_length=255, blank=True)
    etc = models.CharField(max_length=255, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='instructor_infos')
    regions = models.ManyToManyField(Region, blank=True, related_name='instructor_infos')


#____________________________________________________________________________________________________

class InstructorReview(models.Model):
    # 선생님 과외 상세페이지의 리뷰 모델
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="instructor_reviews")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="instructor_reviews")
    
    # 세분화된 리뷰 항목 (0~5점)
    professionalism = models.IntegerField(default=0)  # 전문성
    teaching_skill = models.IntegerField(default=0)   # 강의력
    punctuality = models.IntegerField(default=0)      # 시간 준수
    
    comment = models.TextField(blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='instructor_reviews')

class StudentReview(models.Model):
    # 학생 과외 상세페이지의 리뷰 모델
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="student_reviews")
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="student_reviews")
    rating = models.IntegerField()
    comment = models.TextField(blank=True)

#____________________________________________________________________________________________________

class TutoringResource(models.Model):
    # 수업 리소스 모델
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="tutoring_resources")
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="tutoring_resources")
    
    start_date = models.DateField(blank=True, null=True) # 수업 시작일
    class_type_choices = [
        ("단기 수업", "단기 수업"),
        ("장기 수업", "장기 수업"),
    ]
    class_type = models.CharField(max_length=20, choices=class_type_choices, blank=True) # 수업 유형
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="tutoring_resources", blank=True, null=True) # 수업 과목
    first_month_fee = models.IntegerField(blank=True, null=True) # 첫 달 수업료 (총 수업료)
    
    # 페이백 계좌 관련 필드 (학생)
    payback_bank = models.CharField(max_length=50, blank=True)
    payback_account_number = models.CharField(max_length=50, blank=True)
    payback_account_holder = models.CharField(max_length=50, blank=True)
    
    # 수업료 확인 자료
    fee_confirmation_file = models.FileField(upload_to='fee_confirmations/', blank=True, null=True)
    
    # 양측 확인 필드
    is_student_confirmed = models.BooleanField(default=False)
    is_instructor_confirmed = models.BooleanField(default=False)
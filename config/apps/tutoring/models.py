from django.conf import settings
from django.db import models
from django.db.models import Q
from config.apps.accounts.models import Instructor, Student, Subject
from config.apps.tutoring.constant import REGION_CHOICES, STUDENT_SUBJECT_CHOICES

#____________________________________________________________________________________________________


class Region(models.Model):
    """
    플랫폼에서 지원하는 과외 가능 지역의 마스터 데이터를 관리하는 모델입니다.
    
    학생(구인 공고)과 강사(과외 정보) 양쪽에서 다대다(M:N) 관계로 참조되며,
    REGION_CHOICES 상수를 기준으로 이름이 매핑됩니다.
    
    Attributes:
        number (int): 지역 고유 식별 번호 (REGION_CHOICES 참조).
    """
    number = models.IntegerField(choices=REGION_CHOICES, unique=True)

    def __str__(self):
        return dict(REGION_CHOICES).get(self.number, str(self.number))

#____________________________________________________________________________________________________

from django.core.exceptions import ValidationError

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

def validate_method(value):
    if not value:
        return
    allowed = [choice[0] for choice in method_choices]
    methods = [m.strip() for m in value.split(",") if m.strip()]
    for m in methods:
        if m not in allowed:
            raise ValidationError(f"'{m}' is not a valid choice.")

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
    ("N수생", "N수생"),
    ("재수생", "재수생"),
    ("대학생", "대학생"),
    ("사회인", "사회인"),
]
#____________________________________________________________________________________________________

class TutoringPost(models.Model):
    """
    학생이 작성하는 '과외 선생님 구인 공고' 데이터를 관리하는 모델입니다.
    
    학생이 원하는 과목, 예산, 요일, 과외 형태(대면/비대면) 등의 조건을 명시하며,
    강사들은 이 공고를 보고 제안(Proposal)을 보낼 수 있습니다.
    
    Attributes:
        student (ForeignKey): 공고를 작성한 학생.
        title (str): 공고 제목.
        sex (str): 학생 본인의 성별 또는 원하는 선생님 성별 조건.
        age (int): 학생 본인의 나이.
        grade (str): 학생의 현재 학년 (초1~대학생/사회인).
        field (str): 계열 (문과/이과/예체능 등).
        subjects (ManyToManyField): 과외를 희망하는 과목 목록.
        method (str): 과외 진행 방식 (대면, 비대면 등 콤마 단위로 복수 선택 가능).
        regions (ManyToManyField): 희망 과외 지역.
        cost (int): 학생이 생각하는 예산(금액).
        schedule (str): 희망 요일 및 시간대.
        situation (str): 학생의 현재 학습 상황 및 목표.
        etc (str): 기타 특이사항 또는 요청사항.
        is_active (bool): 공고가 현재 활성화(모집 중) 상태인지 여부.
        view_count (int): 공고 조회수.
        created_at (DateTimeField): 공고 작성 일시.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="tutoring_posts")
    title = models.CharField(max_length=255, blank=True)
    sex = models.CharField(max_length=10, choices=student_sex_choices, blank=True)
    age = models.IntegerField(blank=True, null=True)
    grade = models.CharField(max_length=20, choices=grade_choices, blank=True)
    field = models.CharField(max_length=20, choices=student_field_choices, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='tutoring_posts')
    method = models.CharField(max_length=255, blank=True, validators=[validate_method])
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
    강사가 학생의 과외 공고(TutoringPost)를 '좋아요(관심 등록)'한 내역을 관리하는 모델입니다.
    
    강사(Instructor)와 공고(TutoringPost) 간의 M:N 관계를 해소하는 중간 테이블입니다.
    
    Attributes:
        instructor (ForeignKey): 관심 등록을 한 강사.
        tutoring_post (ForeignKey): 관심 등록 대상이 된 학생의 구인 공고.
        created_at (DateTimeField): 관심 등록 일시.
    """
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='post_likes')
    tutoring_post = models.ForeignKey(TutoringPost, on_delete=models.CASCADE, related_name='liked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('instructor', 'tutoring_post')

class TutoringProposal(models.Model):
    """
    과외 매칭을 위한 '제안서' 데이터를 관리하는 모델입니다.
    
    학생이 특정 강사에게 직접 제안하거나, 강사가 학생의 공고(TutoringPost)를 보고
    먼저 연락할 때 생성되며, 채팅방(ChatRoom) 생성의 매개체가 됩니다.
    
    Attributes:
        tutoring_post (ForeignKey): 제안이 연결된 학생의 구인 공고.
        instructor (ForeignKey): 제안을 보냈거나 받은 강사.
        message (str): 제안을 보낼 때 함께 작성한 첫 메시지.
        created_at (datetime): 제안서가 생성된 시각.
    """
    tutoring_post = models.ForeignKey(TutoringPost, on_delete=models.CASCADE, related_name="proposal")
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="proposals")
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class InstructorInfo(models.Model):
    """
    강사의 과외 상세 프로필(홍보 정보)을 관리하는 모델입니다.
    
    단순한 인증 정보를 담는 Instructor 모델과 달리, 과외비, 희망 시간, 진행 방식 등
    실제로 학생들에게 노출될 구체적인 '과외 모집 정보'를 담당합니다.
    
    Attributes:
        instructor (OneToOneField): 프로필 주체인 강사.
        cost (int): 강사의 희망 과외비(시급/월급 등 기준).
        schedule (str): 과외 가능한 요일 및 시간대.
        method (str): 과외 진행 방식 (대면/비대면).
        location (str): 주 수업 가능 지역 설명 텍스트.
        etc (str): 기타 어필하고 싶은 특이사항.
        subjects (ManyToManyField): 강사가 지도할 수 있는 과목 목록.
        regions (ManyToManyField): 강사가 수업 가능한 지역(마스터 데이터) 목록.
    """
    instructor = models.OneToOneField(Instructor, on_delete=models.CASCADE, related_name="tutoring_profile")
    cost = models.IntegerField(blank=True, null=True)
    schedule = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=255, blank=True, validators=[validate_method])
    location = models.CharField(max_length=255, blank=True)
    etc = models.CharField(max_length=255, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='instructor_infos')
    regions = models.ManyToManyField(Region, blank=True, related_name='instructor_infos')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.instructor and not self.instructor.is_tutoring:
            self.instructor.is_tutoring = True
            self.instructor.save(update_fields=['is_tutoring'])



#____________________________________________________________________________________________________

class InstructorReview(models.Model):
    """
    학생이 강사에게 남기는 '과외 수강 후기' 데이터를 관리하는 모델입니다.
    
    단순한 평균 별점이 아닌 전문성, 강의력, 시간 준수 3가지 세부 지표를 평가합니다.
    
    Attributes:
        instructor (ForeignKey): 리뷰를 받은 강사.
        student (ForeignKey): 리뷰를 작성한 학생.
        professionalism (int): 전문성 점수 (0~5).
        teaching_skill (int): 강의력 점수 (0~5).
        punctuality (int): 시간 준수 점수 (0~5).
        comment (str): 후기 내용.
        created_at (DateTimeField): 리뷰 작성 일시.
        subjects (ManyToManyField): 리뷰와 연관된 과외 수강 과목 목록.
    """
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="instructor_reviews")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="instructor_reviews")
    
    # 세분화된 리뷰 항목 (0~5점)
    professionalism = models.IntegerField(default=0)  # 전문성
    teaching_skill = models.IntegerField(default=0)   # 강의력
    punctuality = models.IntegerField(default=0)      # 시간 준수
    
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='instructor_reviews')

class StudentReview(models.Model):
    """
    강사가 학생에게 남기는 '학습 태도 후기' 데이터를 관리하는 모델입니다.
    
    다른 강사들이 이 학생을 파악할 수 있도록 돕는 매너 온도와 같은 역할을 합니다.
    
    Attributes:
        student (ForeignKey): 리뷰를 받은 학생.
        instructor (ForeignKey): 리뷰를 작성한 강사.
        rating (int): 종합 별점.
        comment (str): 후기 내용 (학생의 태도, 이해력 등).
        created_at (DateTimeField): 리뷰 작성 일시.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="student_reviews")
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="student_reviews")
    rating = models.IntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

#____________________________________________________________________________________________________

class TutoringResource(models.Model):
    """
    최종 성사된 '과외 계약 및 리소스 정보'를 관리하는 모델입니다.
    
    매칭이 성사된 후의 수업 기간, 수업료, 그리고 관리자가 수수료/페이백을
    처리하기 위해 필요한 계좌 정보 및 결제 증빙 자료를 저장합니다.
    
    Attributes:
        student (ForeignKey): 과외를 수강하는 학생.
        instructor (ForeignKey): 과외를 진행하는 강사.
        start_date (DateField): 수업 시작 일자.
        class_type (str): 수업의 유형 (단기 수업, 장기 수업 등).
        subject (ForeignKey): 최종 확정된 수업 과목.
        first_month_fee (int): 책정된 첫 달 수업료.
        payback_bank (str): [학생] 페이백을 받을 은행명.
        payback_account_number (str): [학생] 페이백을 받을 계좌번호.
        payback_account_holder (str): [학생] 페이백 계좌 예금주.
        fee_confirmation_file (FileField): 수업료 입금 확인증 등의 증빙 파일 (단일 파일 필드 - 하위 호환).
        is_student_confirmed (bool): 학생의 계약 정보 최종 확인 여부.
        is_instructor_confirmed (bool): 강사의 계약 정보 최종 확인 여부.
        fee_payment_status (str): 강사의 플랫폼 수수료 납부 상태 (PENDING, PAID 등).
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="tutoring_resources")
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name="tutoring_resources")
    
    start_date = models.DateField(blank=True, null=True) # 수업 시작일
    class_type_choices = [
        ("단기 수업", "단기 수업"),
        ("장기 수업", "장기 수업"),
    ]
    class_type = models.CharField(max_length=20, choices=class_type_choices, blank=True) # 수업 유형
    subject = models.ManyToManyField(Subject, blank=True, related_name='tutoring_resources') # 수업 과목
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

    # 수수료 납부 상태 (선생님이 성사 수수료를 납부하는 플로우)
    FEE_PAYMENT_STATUS_CHOICES = [
        ('PENDING', '입금 대기'),           # 성사 등록 후 아직 입금 전
        ('AWAITING_CONFIRMATION', '확인 대기'),  # 입금 완료 버튼 누른 후
        ('PAID', '납부 완료'),              # 관리자가 입금 확인 후
        ('FAILED', '납부 실패'),            # 입금 미확인 / 기간 초과
    ]
    fee_payment_status = models.CharField(
        max_length=30,
        choices=FEE_PAYMENT_STATUS_CHOICES,
        default='PENDING',
    )

class TutoringResourceFile(models.Model):
    """
    과외 계약(TutoringResource)과 관련된 다수의 첨부 파일을 관리하는 모델입니다.
    
    입금 내역 캡쳐본, 증빙 서류 등 하나의 계약에 여러 장의 이미지가 필요할 때
    Foreign Key로 매핑되어 사용됩니다.
    
    Attributes:
        tutoring_resource (ForeignKey): 파일이 첨부된 대상 계약 정보.
        file (FileField): 업로드된 실제 증빙 파일.
    """
    tutoring_resource = models.ForeignKey(TutoringResource, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to='fee_confirmations/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


class TutoringRegistration(models.Model):
    """채팅방에서 양측이 독립적으로 제출하는 하나의 과외 계약 등록."""

    class AttributeValidationStatus(models.TextChoices):
        UNCHECKED = "UNCHECKED", "미확인"
        MATCHED = "MATCHED", "일치"
        MISMATCHED = "MISMATCHED", "불일치"

    class ContractStatus(models.TextChoices):
        COLLECTING = "COLLECTING", "계약 정보 수집 중"
        REGISTERED = "REGISTERED", "등록 완료"
        ACTIVE = "ACTIVE", "과외 진행 중"
        CANCELLED = "CANCELLED", "취소"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="student_tutoring_registrations",
    )
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="instructor_tutoring_registrations",
    )
    chat_room = models.OneToOneField(
        "chat_app.ChatRoom",
        on_delete=models.PROTECT,
        related_name="tutoring_registration",
    )
    subject = models.CharField(max_length=100)
    start_date = models.DateField()
    attribute_validation_status = models.CharField(
        max_length=20,
        choices=AttributeValidationStatus.choices,
        default=AttributeValidationStatus.UNCHECKED,
    )
    contract_status = models.CharField(
        max_length=20,
        choices=ContractStatus.choices,
        default=ContractStatus.COLLECTING,
    )
    confirmed_class_type = models.CharField(max_length=20, blank=True)
    confirmed_first_month_fee = models.PositiveBigIntegerField(null=True, blank=True)
    terms_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TutoringSubmission(models.Model):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "학생"
        INSTRUCTOR = "INSTRUCTOR", "강사"

    class ClassType(models.TextChoices):
        REGULAR = "REGULAR", "정규 수업"
        SHORT_TERM = "SHORT_TERM", "단기 수업"

    registration = models.ForeignKey(
        TutoringRegistration,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tutoring_submissions",
    )
    class_type = models.CharField(max_length=20, choices=ClassType.choices)
    first_month_fee = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["registration", "role"],
                name="unique_tutoring_submission_per_role",
            ),
        ]


class StudentPaybackAccount(models.Model):
    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "UNVERIFIED", "미인증"
        VERIFIED = "VERIFIED", "인증 완료"
        FAILED = "FAILED", "인증 실패"

    registration = models.OneToOneField(
        TutoringRegistration,
        on_delete=models.PROTECT,
        related_name="student_payback_account",
    )
    bank_code = models.CharField(max_length=20)
    encrypted_account_number = models.TextField()
    account_holder = models.CharField(max_length=30)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CommissionInvoice(models.Model):
    class InvoiceType(models.TextChoices):
        INITIAL = "INITIAL", "최초 수수료"
        ADJUSTMENT = "ADJUSTMENT", "추가 정산"

    class Status(models.TextChoices):
        READY = "READY", "결제 준비"
        PAYMENT_PENDING = "PAYMENT_PENDING", "입금 대기"
        PAID = "PAID", "납부 완료"
        FAILED = "FAILED", "결제 실패"
        CANCELLED = "CANCELLED", "취소"

    registration = models.ForeignKey(
        TutoringRegistration,
        on_delete=models.PROTECT,
        related_name="commission_invoices",
    )
    invoice_type = models.CharField(
        max_length=20,
        choices=InvoiceType.choices,
        default=InvoiceType.INITIAL,
    )
    base_amount = models.PositiveBigIntegerField()
    commission_rate_bps = models.PositiveIntegerField()
    commission_amount = models.PositiveBigIntegerField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.READY)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["registration"],
                condition=Q(invoice_type="INITIAL"),
                name="unique_initial_commission_invoice",
            ),
        ]


class VirtualAccountPayment(models.Model):
    class FeePaymentStatus(models.TextChoices):
        ISSUING = "ISSUING", "가상계좌 발급 중"
        WAITING_FOR_DEPOSIT = "WAITING_FOR_DEPOSIT", "입금 대기"
        DONE = "DONE", "납부 완료"
        FAILED = "FAILED", "결제 처리 실패"
        EXPIRED = "EXPIRED", "입금 기한 만료"
        CANCELLED = "CANCELLED", "결제 취소"

    invoice = models.ForeignKey(
        CommissionInvoice,
        on_delete=models.PROTECT,
        related_name="virtual_account_payments",
    )
    order_id = models.CharField(max_length=64, unique=True)
    payment_key = models.CharField(max_length=200, null=True, blank=True, unique=True)
    expected_amount = models.PositiveBigIntegerField()
    bank_code = models.CharField(max_length=20, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    account_holder = models.CharField(max_length=100, blank=True)
    toss_secret = models.TextField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    fee_payment_status = models.CharField(
        max_length=30,
        choices=FeePaymentStatus.choices,
        default=FeePaymentStatus.ISSUING,
    )
    toss_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TossWebhookEvent(models.Model):
    transaction_key = models.CharField(max_length=200, unique=True)
    order_id = models.CharField(max_length=64)
    event_status = models.CharField(max_length=30)
    payload = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)

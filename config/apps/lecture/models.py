from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from config.apps.accounts.models import Instructor, Student, Subject


class Lecture(models.Model):
    """
    강사가 업로드한 'VOD 강의' 데이터를 관리하는 모델입니다.
    
    학생들은 보유한 캐시를 소모하여 이 강의를 대여(Rental)하고,
    할당된 기간(rental_period) 동안 비디오 스트리밍을 시청할 수 있습니다.
    
    Attributes:
        video (FileField): 실제 강의 비디오 파일.
        video_duration (int): 비디오 재생 시간(초 단위).
        thumbnail (ImageField): 강의 썸네일 이미지.
        title (str): 강의 제목.
        subjects (ManyToManyField): 강의가 속한 과목 목록.
        price (int): 강의 대여 가격 (인앱 화폐인 '캐시' 기준).
        instructor (ForeignKey): 강의를 제작 및 업로드한 강사.
        is_preview (bool): 무료로 볼 수 있는 맛보기(Preview) 강의인지 여부.
        view_count (int): 강의 상세페이지 조회수.
        likes (ManyToManyField): 강의를 '좋아요(찜)'한 학생 목록.
        rental_period (int): 결제 시 부여되는 대여 기간 (단위: 일).
        created_at (DateTimeField): 강의 업로드 일시.
        is_active (bool): 강의 활성화(노출) 여부.
        is_delete (bool): 강사에 의해 삭제(Soft Delete) 처리되었는지 여부.
        deleted_at (DateTimeField): 삭제 처리된 일시.
    """
    video = models.FileField(upload_to="lectures/videos/")
    video_duration = models.PositiveIntegerField(default=0)
    thumbnail = models.ImageField(upload_to="lectures/thumbnails/")
    title = models.CharField(max_length=255)
    subjects = models.ManyToManyField(Subject, blank=True, related_name="lectures")
    price = models.PositiveIntegerField(default=0)  # 단위: 캐시 (인앱 화폐)
    instructor = models.ForeignKey(
        Instructor, on_delete=models.CASCADE, related_name="lectures"
    )
    is_preview = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)
    likes = models.ManyToManyField(Student, blank=True, related_name="liked_lectures")
    rental_period = models.PositiveIntegerField(default=30, help_text="대여 기간 (일)")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_delete = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class Comment(models.Model):
    """
    강의(VOD) 하단에 달리는 '질문 및 댓글' 데이터를 관리하는 모델입니다.
    
    학생이 질문을 남기고 강사가 답변을 달거나, 학생들끼리 의견을 나눌 수 있습니다.
    Self-Referencing을 통해 대댓글(Reply)을 지원하지만, 
    대대댓글(Depth 2 이상)은 모델의 clean() 메서드를 통해 구조적으로 차단합니다.
    
    Attributes:
        lecture (ForeignKey): 댓글이 작성된 대상 강의.
        author (ForeignKey): 댓글을 작성한 사용자(강사/학생 무관).
        parent (ForeignKey): 상위 댓글 (대댓글인 경우).
        content (str): 댓글 내용.
        referenced_person (ForeignKey): "@멘션" 기능을 통해 지목된 사용자.
        created_at (DateTimeField): 댓글 작성 일시.
    """
    lecture = models.ForeignKey(
        Lecture, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecture_comments"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    content = models.TextField()
    referenced_person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referenced_in_comments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        # parent가 같은 lecture에 속하는지 검증
        if self.parent and self.parent.lecture_id != self.lecture_id:
            raise ValidationError("대댓글은 같은 강의의 댓글에만 달 수 있습니다.")
        # 대대댓글 금지: parent가 이미 reply(=parent가 있는 댓글)이면 불가
        if self.parent and self.parent.parent_id is not None:
            raise ValidationError("대댓글에 대한 답글은 허용되지 않습니다.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Comment by {self.author} on {self.lecture}"


class SearchHistory(models.Model):
    """
    학생이 입력한 '강의/강사 검색어' 기록을 관리하는 모델입니다.
    
    사용자 경험(UX) 향상을 위해 홈 화면 등에서 '최근 검색어'를 제공하기 위해 쓰이며,
    SearchHistoryCreateAPIView 로직에 의해 학생당 최대 5개까지만 유지되도록 자동 롤링됩니다.
    
    Attributes:
        student (ForeignKey): 검색을 수행한 학생.
        query (str): 사용자가 입력한 검색 키워드.
        created_at (DateTimeField): 검색을 수행한 일시 (정렬 및 오래된 기록 삭제 기준).
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="search_histories",
    )
    query = models.CharField(max_length=255)  # 검색 키워드
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]  # 최신순 정렬

    def __str__(self):
        return f"{self.student} — {self.query}"

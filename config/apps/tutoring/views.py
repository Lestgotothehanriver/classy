from rest_framework import generics, permissions, viewsets  # DRF의 제네릭 뷰 + 권한
from rest_framework.response import Response  # 응답 객체
from rest_framework.views import APIView  # 간단한 APIView도 사용
from django.db.models import Avg, Count  # annotate(집계)용
from django.shortcuts import get_object_or_404  # 404 처리 포함한 조회 함수

from config.apps.accounts.models import Instructor, Student  # accounts의 모델
from .models import TutoringPost, InstructorInfo, InstructorReview, StudentReview  # tutoring 모델들
from .serializers import (  # 우리가 만든 serializers
    InstructorListSerializer,
    InstructorInfoSerializer,
    InstructorReviewSerializer,
    TutoringPostListSerializer,
    TutoringPostDetailSerializer,
    StudentReviewSerializer,
    StudentMyPostSerializer,
)


# ____________________________________________________________________________________
# 공통 유틸: 쿼리 파라미터 "1,2,3" 같은 콤마 문자열 -> int 리스트
# ____________________________________________________________________________________
def parse_int_list(value):  # value는 문자열 또는 None
    if not value:  # 값이 없으면
        return []  # 빈 리스트
    return [int(x) for x in value.split(",") if x.strip().isdigit()]  # "1,2" -> [1,2]


# ____________________________________________________________________________________
# 공통 유틸: 모델에 특정 필드가 있는지 확인
# ____________________________________________________________________________________
def has_field(model_cls, field_name):  # model_cls는 Instructor/Student 같은 모델 클래스
    return any(f.name == field_name for f in model_cls._meta.get_fields())  # 필드명이 있으면 True


# ____________________________________________________________________________________
# 공통 유틸: "좋아요" 기반 정렬을 가능한 범위에서 자동 적용
# - like_count 필드가 있으면 그걸 사용
# - likes / liked_by 같은 M2M가 있으면 Count로 annotate 후 사용
# - 아무것도 없으면 id 최신순으로라도 정렬
# ____________________________________________________________________________________
def order_by_likes(qs, model_cls):  # qs는 QuerySet, model_cls는 그 QuerySet의 모델
    field_names = {f.name for f in model_cls._meta.get_fields()}  # 모델의 모든 필드 이름 집합

    if "like_count" in field_names:  # like_count 정수 필드가 있으면
        return qs.order_by("-like_count", "-id")  # like_count 내림차순 -> 동률이면 최신순

    for candidate in ["likes", "liked_by", "like_users"]:  # 흔히 쓰는 M2M 후보 이름들
        if candidate in field_names:  # 해당 이름의 필드가 실제로 존재하면
            return qs.annotate(  # 좋아요 개수를 annotate로 붙이고
                like_count=Count(candidate, distinct=True)
            ).order_by("-like_count", "-id")  # 그걸로 정렬

    return qs.order_by("-id")  # 좋아요 구조를 못 찾으면 최소한 최신순


# ____________________________________________________________________________________
# 공통 유틸: Instructor/Student에서 "Subject 관계"를 자동으로 찾아 필터 적용
# (직접 M2M이든, 중간모델이든 최대한 대응)
# ____________________________________________________________________________________
def apply_subject_filter(qs, owner_model, subject_ids, prefix=""):  # prefix는 join 경로(예: "student__")
    """Subject M2M 필드를 기준으로 QuerySet 필터 적용."""
    if not subject_ids:
        return qs
    key = f"{prefix}subjects__id__in"
    return qs.filter(**{key: subject_ids}).distinct()


# ____________________________________________________________________________________
# 학생 페이지
# 1) 강사 list (최신순 기본, 좋아요순 선택)
# 2) 강사 조회(필터)
# ____________________________________________________________________________________
class InstructorListAPIView(generics.ListAPIView):  # GET /tutoring/instructors/
    """
        URL
        - GET /tutoring/instructors/

        Query Params (선택)
        - ordering=latest|likes    # 정렬 기준 (기본: latest)
        - subject=1,2,3            # 콤마로 여러 과목 id
        - region=서울|강남구
        - cost=200000              # 해당 금액 이하 (gte에서 lte 기반으로 변경)
        - method=대면              # or 비대면
        - sex=남성                 # Instructor에 sex 필드 있을 때만
        - age=25                   # 5살 단위 버킷 (user__birth_date 연도 계산 기반)
        - min_rating=4
        - university=UNIST
        - department=컴퓨터공학       # 학과 부분검색
        - student_id=2024

        Example Request
        - GET /tutoring/instructors/?subject=1,3&region=2&cost=200000&method=대면&sex=여성&age=25&min_rating=4&university=UNIST&department=컴퓨터공학&student_id=2024

        Example Response (200)
        [
        {
            "id": 12,                      // int
            "name": "Jane Smith",          // string
            "avg_rating": 4.6,             // float (nullable)
            "review_count": 18,            // int
            "like_count": 103,             // int
            "university": "UNIST",         // string
            "region": "서울|강남구"          // string (nullable)
        },
        {
            "id": 7,                       // int
            "name": "Kim",                 // string
            "avg_rating": 4.2,             // float (nullable)
            "review_count": 5,             // int
            "like_count": 77,              // int
            "university": "UNIST",         // string
            "region": "서울|강남구"          // string (nullable)
        }
        ]
        """
    permission_classes = [permissions.AllowAny]  # 필요하면 IsAuthenticated로 바꿔도 됨
    serializer_class = InstructorListSerializer  # 리스트용 serializer 지정

    def get_queryset(self):  # 리스트에서 사용할 queryset을 만드는 함수
        from django.db.models import F, ExpressionWrapper, FloatField, Exists, OuterRef, Value, BooleanField
        from config.apps.accounts.models import InstructorLike, Student
        qs = Instructor.objects.all()  # 전체 강사 가져오기

        qs = qs.select_related("tutoring_profile") if hasattr(Instructor, "tutoring_profile") else qs  # 1:1 있으면 최적화

        student = None
        if self.request.user.is_authenticated:
            student = Student.objects.filter(user=self.request.user).first()

        if student:
            qs = qs.annotate(
                is_liked=Exists(
                    InstructorLike.objects.filter(
                        student=student,
                        instructor=OuterRef("pk")
                    )
                )
            )
        else:
            qs = qs.annotate(is_liked=Value(False, output_field=BooleanField()))

        qs = qs.annotate(  # 리뷰 기반 집계 필드 추가: (전문성 + 강의력 + 시간 준수) / 3 의 평균
            avg_rating=Avg(
                ExpressionWrapper(
                    (F("instructor_reviews__professionalism") + 
                     F("instructor_reviews__teaching_skill") + 
                     F("instructor_reviews__punctuality")) / 3.0,
                    output_field=FloatField()
                )
            ),
            review_count=Count("instructor_reviews", distinct=True),  # InstructorReview 개수
            like_count=Count("liked_by", distinct=True),  # InstructorLike 좋아요 개수 (항상 어노테이트)
        )  # annotate 결과는 serializer에서 읽기 전용으로 사용

        ordering = self.request.query_params.get("ordering", "latest")  # 기본값: 최신순
        if ordering == "likes":  # ?ordering=likes 이면 좋아요순
            qs = qs.order_by("-like_count", "-id")  # 좋아요순 → 동률이면 최신순
        else:  # latest(기본값) 또는 기타 → 최신순
            qs = qs.order_by("-id")

        liked = self.request.query_params.get("liked")
        if liked is not None:
            qs = qs.filter(is_liked=(liked.lower() in ("true", "1")))

        subject_ids = parse_int_list(self.request.query_params.get("subject"))  # ?subject=1,2 같은 값 파싱
        qs = apply_subject_filter(qs, Instructor, subject_ids)  # Instructor의 Subject 구조를 자동 탐색해 필터

        region = self.request.query_params.get("region")  # ?region=서울|강남구 같은 값
        if region:  # region 파라미터가 있으면
            if has_field(Instructor, "region"):  # Instructor에 region 필드가 있으면
                qs = qs.filter(region__icontains=region)  # 포함 검색
            else:  # Instructor에 region이 없으면
                qs = qs.filter(tutoring_profile__location__icontains=region)  # InstructorInfo.location으로 검색(있다는 가정)

        cost = self.request.query_params.get("cost")
        if cost and cost.isdigit():
            qs = qs.filter(tutoring_profile__cost__lte=int(cost))

        method = self.request.query_params.get("method")  # ?method=대면 or 비대면
        if method:  # 값이 있으면
            qs = qs.filter(tutoring_profile__method=method)  # InstructorInfo.method 필터

        sex = self.request.query_params.get("sex")  # ?sex=남성/여성
        if sex:  # 값이 있으면
            qs = qs.filter(user__sex=sex)  # sex는 User 모델 필드이므로 user__ 경유

        age = self.request.query_params.get("age")
        if age and age.isdigit():
            from django.utils import timezone
            base_age = (int(age) // 5) * 5
            current_year = timezone.now().year
            min_year = current_year - (base_age + 4)
            max_year = current_year - base_age
            qs = qs.filter(user__birth_date__year__gte=min_year, user__birth_date__year__lte=max_year)

        min_rating = self.request.query_params.get("min_rating")  # ?min_rating=4
        if min_rating and min_rating.isdigit():  # 숫자면
            qs = qs.filter(avg_rating__gte=float(min_rating))  # annotate된 avg_rating 기준으로 필터

        university = self.request.query_params.get("university")  # ?university=UNIST 같은 값
        if university:  # 값이 있으면
            for f in ["university", "school", "school_name"]:  # 흔한 후보 필드명들
                if has_field(Instructor, f):  # 실제로 있으면
                    qs = qs.filter(**{f"{f}__icontains": university})  # 부분검색
                    break  # 첫 매칭 필드로만 적용하고 종료

        department = self.request.query_params.get("department")  # ?department=컴퓨터공학 같은 값
        if department:  # 값이 있으면
            qs = qs.filter(department__icontains=department)  # Instructor.department 부분검색

        student_no = self.request.query_params.get("student_id")  # ?student_id=2024 같은 값(학번)
        if student_no:  # 값이 있으면
            for f in ["student_id", "student_no", "school_id", "student_number"]:  # 흔한 후보들
                if has_field(Instructor, f):  # 실제 필드가 있으면
                    qs = qs.filter(**{f"{f}__icontains": student_no})  # 부분검색
                    break  # 하나만 적용

        return qs  # 최종 queryset 반환



# ____________________________________________________________________________________
# 학생 페이지
# 강사 세부 탭: 과외 정보(InstructorInfo)
# ____________________________________________________________________________________
class InstructorInfoAPIView(generics.RetrieveAPIView):  # GET /tutoring/instructors/<id>/info/
    """
    URL
    - GET /tutoring/instructors/<int:instructor_id>/info/

    Path Params
    - instructor_id: Instructor id

    Example Request
    - GET /tutoring/instructors/13/info/

    Example Response (200)
    {
    "id": 3,                       // int
    "instructor": 12,              // int
    "cost": 250000,                // int (nullable)
    "schedule": "주말 오후",            // string (nullable)
    "method": "대면",                // string (nullable)
    "location": "서울|강남구",          // string (nullable)
    "etc": "수학/물리 전문. 커리큘럼 맞춤형.", // string (nullable)
    "instruction": "저는 어쩌고 저쩌고...",  // string (nullable)
    "subjects": [                  // list of objects
        {"id": 33, "label": "수학"},
        {"id": 36, "label": "물리"}
    ],
    "regions": [                   // list of objects
        {"id": 1, "label": "서울|강남구"}
    ]
    }
    """
    permission_classes = [permissions.AllowAny]  # 필요하면 인증
    serializer_class = InstructorInfoSerializer  # InstructorInfo serializer

    def retrieve(self, request, *args, **kwargs):
        instructor_id = self.kwargs.get("instructor_id")
        qs = InstructorInfo.objects.select_related("instructor").prefetch_related("subjects", "regions")
        instance = qs.filter(instructor_id=instructor_id).first()
        
        if not instance:
            return Response({})  # 404 대신 빈 객체 반환
            
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

# ____________________________________________________________________________________
# 학생 페이지
# 강사 세부 탭: 과외 리뷰(InstructorReview)
# ____________________________________________________________________________________
class InstructorReviewListAPIView(generics.ListAPIView):  # GET /tutoring/instructors/<id>/reviews/
    """
    URL
    - GET /tutoring/instructors/<int:instructor_id>/reviews/

    Path Params
    - instructor_id: Instructor id

    Example Request
    - GET /tutoring/instructors/12/reviews/

    Example Response (200)
    [
    {
        "id": 55,                      // int
        "instructor": 12,              // int
        "student": 9,                  // int
        "professionalism": 5,          // int
        "teaching_skill": 4,           // int
        "punctuality": 5,              // int
        "comment": "설명 진짜 깔끔하고 좋았음", // string (nullable)
        "created_at": "2026-02-10T12:30:00+09:00" // date string
    },
    {
        "id": 41,                      // int
        "instructor": 12,              // int
        "student": 10,                 // int
        "professionalism": 4,          // int
        "teaching_skill": 4,           // int
        "punctuality": 4,              // int
        "comment": "수업 자료가 알찼음",       // string (nullable)
        "created_at": "2026-01-28T19:10:00+09:00" // date string
    }
    ]
"""
    permission_classes = [permissions.AllowAny]  # 필요하면 인증
    serializer_class = InstructorReviewSerializer  # 리뷰 serializer

    def get_queryset(self):  # 해당 강사의 리뷰 목록만 반환
        instructor_id = self.kwargs["instructor_id"]  # URL에서 instructor_id 얻기
        return InstructorReview.objects.filter(instructor_id=instructor_id).order_by("-id")  # 최신순


# ____________________________________________________________________________________
# 강사 페이지
# 1) 공고 list (최신순 기본, 좋아요순 선택, 실제 리소스는 TutoringPost)
# 2) 공고 조회(필터)
# ____________________________________________________________________________________
class TutoringPostListAPIView(generics.ListAPIView):  # GET /tutoring/posts/
    """
    URL
    - GET /tutoring/posts/

    Query Params (선택)
    - ordering=latest|likes    # 정렬 기준 (기본: latest)
    - subject=1,2,3
    - region=서울|강남구
    - cost=200000              # 해당 금액 이하 (gte에서 lte 기반으로 변경)
    - method=대면              # or 비대면
    - sex=남성                 # 공고 필드
    - grade=고3                # 공고 필드 (유치원생, 초1~6, 중1~3, 고1~3, 재수생, 사회인)

    Example Request
    - GET /tutoring/posts/?subject=2&region=서울|강남구&cost=300000&method=비대면&sex=여성&grade=고3&age_group=20s&min_rating=4

    Example Response (200)
    [
    {
        "id": 101,                     // int
        "student": 9,                  // int
        "student_name": "김민수",        // string
        "student_age": 25,             // int (nullable)
        "student_sex": "여성",           // string (nullable)
        "student_field": "문과",         // string (nullable)
        "tutoring_post_sex": "남성",     // string (nullable)
        "tutoring_post_age": 24,       // int (nullable)
        "grade": "고3",                  // string (nullable)
        "tutoring_post_region": 1,     // int (nullable)
        "tutoring_post_subject": [1,2,3] // list of ints (nullable)
        
    },
    {
        "id": 88,                      // int
        "student": 15,                 // int
        "region": "서울|강남구",          // string (nullable)
        "sex": "여성",                   // string (nullable)
        "like_count": 41,              // int
        "is_active": true              // boolean
    }
    ]
"""
    permission_classes = [permissions.AllowAny]  # 필요하면 인증
    serializer_class = TutoringPostListSerializer  # 리스트 serializer

    def get_queryset(self):  # queryset 구성
        qs = TutoringPost.objects.filter(is_active=True).select_related("student")  # 활성 공고 + student join

        qs = qs.annotate(  # 학생 리뷰 통계(학생 프로필에 붙여서 보여주기 위함)
            student_avg_rating=Avg("student__student_reviews__rating"),  # StudentReview.rating 평균
            student_review_count=Count("student__student_reviews", distinct=True),  # StudentReview 개수
            like_count=Count("liked_by", distinct=True),  # TutoringPostLike 좋아요 개수 (항상 어노테이트)
        )  # annotate 결과는 serializer에서 read_only로 사용

        ordering = self.request.query_params.get("ordering", "latest")  # 기본값: 최신순
        if ordering == "likes":  # ?ordering=likes 이면 좋아요순
            qs = qs.order_by("-like_count", "-id")  # 좋아요순 → 동률이면 최신순
        else:  # latest(기본값) 또는 기타 → 최신순
            qs = qs.order_by("-id")

        subject_ids = parse_int_list(self.request.query_params.get("subject"))  # ?subject=1,2 (StudentSubject 기반)
        qs = apply_subject_filter(qs, Student, subject_ids, prefix="student__")  # student 쪽 subject 구조로 필터

        region = self.request.query_params.get("region")  # ?region=서울|강남구
        if region:  # 값이 있으면
            qs = qs.filter(region__icontains=region)  # 공고의 region 문자열에서 포함검색

        cost = self.request.query_params.get("cost")
        if cost and cost.isdigit():
            qs = qs.filter(cost__lte=int(cost))

        method = self.request.query_params.get("method")  # ?method=대면/비대면
        if method:  # 값이 있으면
            qs = qs.filter(method=method)  # 공고의 method 필터

        sex = self.request.query_params.get("sex")  # ?sex=남성/여성
        if sex:  # 값이 있으면
            qs = qs.filter(sex=sex)  # 공고의 sex 필터

        grade = self.request.query_params.get("grade")  # ?grade=초1/고3 등
        if grade:
            qs = qs.filter(grade=grade)


        min_rating = self.request.query_params.get("min_rating")  # ?min_rating=4 (학생 리뷰 평균 기준)
        if min_rating and min_rating.isdigit():  # 숫자면
            qs = qs.filter(student_avg_rating__gte=float(min_rating))  # annotate된 평균 별점 기준 필터

        return qs  # 최종 queryset 반환


# ____________________________________________________________________________________
# 강사 페이지
# 3) 공고 세부 페이지 조회
# - 최초: 공고 상세(=과외 공고 탭)
# - 추가 GET: 해당 학생의 리뷰(=과외 리뷰 탭)
# ____________________________________________________________________________________
class TutoringPostDetailAPIView(generics.RetrieveAPIView):  # GET /tutoring/posts/<id>/
    """
    URL
    - GET /tutoring/posts/<int:pk>/

    Path Params
    - pk: TutoringPost id

    Example Request
    - GET /tutoring/posts/101/

    Example Response (200)
    {
    "id": 101,                     // int
    "student": {
        "id": 9,                   // int
        "name": "Lee",             // string
        "university": "UNIST"      // string
    },
    "title": "미적분 과외 구합니다",      // string
    "content": "주 2회, 개념부터 문제풀이까지 원해요", // string (nullable)
    "region": "서울|강남구",           // string (nullable)
    "cost": 300000,                // int (nullable)
    "method": "비대면",               // string (nullable)
    "sex": "여성",                    // string (nullable)
    "grade": "고3",                   // string (nullable)
    "is_active": true,             // boolean
    "created_at": "2026-02-05T10:00:00+09:00" // date string
    }
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = TutoringPostDetailSerializer
    queryset = TutoringPost.objects.select_related("student")

    def retrieve(self, request, *args, **kwargs):
        from django.db.models import F
        # 조회수를 race condition 없이 atomic하게 +1
        TutoringPost.objects.filter(pk=kwargs["pk"]).update(view_count=F("view_count") + 1)
        return super().retrieve(request, *args, **kwargs)

#____________________________________________________________________________________
# 학생 리뷰 조회
# - 특정 학생의 리뷰 리스트 반환
# ____________________________________________________________________________________
class StudentReviewListAPIView(generics.ListAPIView):  # GET /tutoring/students/<id>/reviews/
    """
    URL
    - GET /tutoring/students/<int:student_id>/reviews/

    Path Params
    - student_id: Student id

    Example Request
    - GET /tutoring/students/9/reviews/

    Example Response (200)
    [
    {
        "id": 77,                      // int
        "student": 9,                  // int
        "rating": 5,                   // int
        "content": "약속 잘 지키고 커뮤니케이션 좋아요", // string (nullable)
        "created_at": "2026-01-12T21:00:00+09:00" // date string
    },
    {
        "id": 61,                      // int
        "student": 9,                  // int
        "rating": 4,                   // int
        "content": "수업 태도 좋았음",         // string (nullable)
        "created_at": "2025-12-20T18:30:00+09:00" // date string
    }
    ]
    """
    permission_classes = [permissions.AllowAny]  # 필요하면 인증
    serializer_class = StudentReviewSerializer  # 학생 리뷰 serializer

    def get_queryset(self):  # 해당 학생의 리뷰만 가져오기
        student_id = self.kwargs["student_id"]  # URL에서 student_id 얻기
        return StudentReview.objects.filter(student_id=student_id).order_by("-id")  # 그 학생의 리뷰 최신순

from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from .serializers import (
    InstructorInfoWriteSerializer,
    InstructorReviewWriteSerializer,
    TutoringPostWriteSerializer,
    StudentReviewWriteSerializer,
)
from config.apps.accounts.models import Instructor



# ____________________________________________________________________________________
# 강사 과외정보 (InstructorInfo) — Create / Patch / Delete
# ____________________________________________________________________________________

class InstructorInfoViewSet(mixins.CreateModelMixin,
                             mixins.UpdateModelMixin,
                             mixins.DestroyModelMixin,
                             GenericViewSet):
    """
    POST   /tutoring/instructor-info/          강사 과외정보 생성
    PATCH  /tutoring/instructor-info/<pk>/     강사 과외정보 수정
    DELETE /tutoring/instructor-info/<pk>/     강사 과외정보 삭제

  


    * 본인 계정의 InstructorInfo만 조작 가능.

    Request (POST / PATCH):
    {
        "cost": 250000,
        "schedule": "주말 오후",
        "method": "대면",
        "location": "서울 강남구",
        "etc": "수학 전문",
        "subjects": [33, 36],
        "regions": [1, 2]
    }

    Response (POST/PATCH 200/201):
    {
        "id": 5,                       // int
        "instructor": 12,              // int
        "cost": 250000,                // int (nullable)
        "schedule": "주말 오후",            // string (nullable)
        "method": "대면",                // string (nullable)
        "location": "서울 강남구",           // string (nullable)
        "etc": "수학 전문"                // string (nullable)
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorInfoWriteSerializer

    def get_queryset(self):
        return InstructorInfo.objects.filter(instructor__user=self.request.user)

    def perform_create(self, serializer):
        instructor = get_object_or_404(Instructor, user=self.request.user)
        serializer.save(instructor=instructor)


# ____________________________________________________________________________________
# 강사 리뷰 (InstructorReview) — Create / Patch / Delete
# ____________________________________________________________________________________

class InstructorReviewViewSet(mixins.CreateModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.DestroyModelMixin,
                               GenericViewSet):
    """
    POST   /tutoring/reviews/instructor/         강사 리뷰 작성 (학생만)
    PATCH  /tutoring/reviews/instructor/<pk>/    강사 리뷰 수정 (작성자만)
    DELETE /tutoring/reviews/instructor/<pk>/    강사 리뷰 삭제 (작성자만)

    Path Params:
    - pk: InstructorReview id

    Request (POST):
    {
        "instructor": 12,
        "professionalism": 5,
        "teaching_skill": 4,
        "punctuality": 5,
        "comment": "설명이 정말 좋았어요!",
        "subjects": [33]
    }

    Response (POST/PATCH 200/201):
    {
        "id": 1,                       // int
        "instructor": 12,              // int
        "student": 9,                  // int
        "professionalism": 5,          // int
        "teaching_skill": 4,           // int
        "punctuality": 5,              // int
        "comment": "설명이 정말 좋았어요!",     // string (nullable)
        "created_at": "2026-03-04T12:00:00Z" // date string
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorReviewWriteSerializer

    def get_queryset(self):
        return InstructorReview.objects.filter(student__user=self.request.user)

    def perform_create(self, serializer):
        from config.apps.accounts.models import Student
        from rest_framework.exceptions import PermissionDenied
        print("AUTH HEADER:", self.request.headers.get("Authorization"))
        try:
            student = Student.objects.get(user=self.request.user)
        except Student.DoesNotExist:
            raise PermissionDenied("학생 계정만 강사 리뷰를 작성할 수 있습니다.")
        serializer.save(student=student)


# ____________________________________________________________________________________
# 과외 공고 (TutoringPost) — Create / Patch / Delete
# ____________________________________________________________________________________

class TutoringPostViewSet(mixins.CreateModelMixin,
                          mixins.UpdateModelMixin,
                          mixins.DestroyModelMixin,
                          GenericViewSet):
    """
    POST   /tutoring/posts/write/          공고 생성 (학생만)
    PATCH  /tutoring/posts/write/<pk>/     공고 수정 (작성자만)
    DELETE /tutoring/posts/write/<pk>/     공고 삭제 (작성자만)

    Path Params:
    - pk: TutoringPost id

    Request (POST / PATCH):
    {
        "title": "미적분 과외 구합니다",
        "sex": "여성",
        "grade": "고3",
        "field": "이과",
        "method": "대면",
        "region": "서울 강남구",
        "cost": 300000,
        "schedule": "주 2회 주말",
        "situation": "고3 수능 준비",
        "etc": "강남역 근처 가능",
        "is_active": true,
        "subjects": [36, 37],
        "regions": [1, 15]
    }

    Response (POST/PATCH 200/201):
    {
        "id": 101,                      // int
        "title": "미적분 과외 구합니다",      // string
        "sex": "여성",                    // string (nullable)
        "grade": "고3",                   // string (nullable)
        "field": "이과",                  // string (nullable)
        "method": "대면",                 // string (nullable)
        "region": "서울 강남구",            // string (nullable)
        "cost": 300000,                 // int (nullable)
        "schedule": "주 2회 주말",           // string (nullable)
        "situation": "고3 수능 준비",        // string (nullable)
        "etc": "강남역 근처 가능",             // string (nullable)
        "is_active": true               // boolean
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringPostWriteSerializer

    def get_queryset(self):
        return TutoringPost.objects.filter(student__user=self.request.user)

    def perform_create(self, serializer):
        from config.apps.accounts.models import Student
        student = get_object_or_404(Student, user=self.request.user)
        serializer.save(student=student)


# ____________________________________________________________________________________
# 학생 리뷰 (StudentReview) — Create / Patch / Delete
# ____________________________________________________________________________________

class StudentReviewViewSet(mixins.CreateModelMixin,
                            mixins.UpdateModelMixin,
                            mixins.DestroyModelMixin,
                            GenericViewSet):
    """
    POST   /tutoring/reviews/student/         학생 리뷰 작성 (강사만)
    PATCH  /tutoring/reviews/student/<pk>/    학생 리뷰 수정 (작성자만)
    DELETE /tutoring/reviews/student/<pk>/    학생 리뷰 삭제 (작성자만)

    Path Params:
    - pk: StudentReview id

    Request (POST):
    {
        "student": 9,
        "rating": 5,
        "comment": "약속도 잘 지키고 성실했어요!"
    }

    Response (POST/PATCH 200/201):
    {
        "id": 2,                       // int
        "student": 9,                  // int
        "rating": 5,                   // int
        "comment": "약속도 잘 지키고 성실했어요!", // string (nullable)
        "created_at": "2026-03-04T12:00:00Z" // date string
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentReviewWriteSerializer

    def get_queryset(self):
        return StudentReview.objects.filter(instructor__user=self.request.user)

    def perform_create(self, serializer):
        instructor = get_object_or_404(Instructor, user=self.request.user)
        serializer.save(instructor=instructor)


# ____________________________________________________________________________________
# 학생 -> 강사: 과외 공고 기반 채팅방 생성 API
# ____________________________________________________________________________________

from rest_framework.views import APIView
from rest_framework import status
from config.apps.chat_app.models import ChatRoom
import logging
logger = logging.getLogger(__name__)

class StudentProposeToInstructorAPIView(APIView):
    """
    POST /tutoring/propose-to-instructor/
    학생이 선생님 프로필을 보고, 본인의 과외 공고를 선택해 채팅방을 엽니다.
    
    Request:
    { 
        "instructor_id": 1,
        "post_id": 101
    }

    Response (200/201):
    {
        "post_id": 101                 // int
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        instructor_id = request.data.get("instructor_id")
        post_id = request.data.get("post_id")

        if not instructor_id or not post_id:
            return Response({"error": "instructor_id and post_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        # 학생 검증 (작성된 공고의 주인이 맞는지도 확인)
        try:
            student = Student.objects.get(user=request.user)
        except Student.DoesNotExist:
            return Response({"error": "학생 계정만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        instructor = get_object_or_404(Instructor, id=instructor_id)
        post = get_object_or_404(TutoringPost, id=post_id, student=student)

        # 채팅방 생성 또는 조회
        room, created = ChatRoom.objects.get_or_create(
            student=student,
            instructor=instructor,
            post=post,
            defaults={"title": f"과외 문의 - {student.user.username}님 & {instructor.user.username}님"}
        )

        # 새로 생성된 경우 → 강사에게 FCM 발송 (채팅 목록 실시간 갱신)
        if created:
            try:
                from config.apps.chat_app.notifications import push_to_users
                from config.apps.notification.models import Notification
                title = room.title
                body = f"{student.user.username}님이 과외를 제안했습니다."
                data = {"type": "new_room", "room_id": str(room.id)}
                Notification.objects.create(
                    user=instructor.user, type="new_room", title=title, body=body, data=data
                )
                push_to_users(
                    [instructor.user.id], title=title, body=body,
                    username=student.user.username, data=data
                )
            except Exception:
                pass  # FCM 실패는 무시

        return Response({
            "room_id": room.id,
            "post_id": post.id,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ____________________________________________________________________________________
# 강사 -> 학생: 과외 제안서 전송 및 채팅방 생성 API
# ____________________________________________________________________________________

class InstructorProposeToStudentAPIView(APIView):
    """
    POST /tutoring/propose-to-student/
    선생님이 학생의 공고를 보고, 과외 제안서를 보내면서 채팅방을 생성합니다.
    
    Request:
    { 
        "post_id": 4,
        "message": "안녕하세요"
    }

    Response (201):
    {
        "instructor_id": 1             // int
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        post_id = request.data.get("post_id")
        message = request.data.get("message", "")

        if not post_id:
            return Response({"error": "post_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        # 강사 검증
        try:
            instructor = Instructor.objects.get(user=request.user)
        except Instructor.DoesNotExist:
            return Response({"error": "선생님 계정만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(TutoringPost, id=post_id)

        # 제안서 생성
        from .models import TutoringProposal
        proposal = TutoringProposal.objects.create(
            tutoring_post=post,
            instructor=instructor,
            message=message
        )

        # 채팅방 생성 또는 조회
        room, created = ChatRoom.objects.get_or_create(
            student=post.student,
            instructor=instructor,
            post=post,
            defaults={"title": f"제안서 문의 - {post.student.user.username}님 & {instructor.user.username}님"}
        )

        # 새로 생성된 경우 → 학생에게 FCM 발송 (채팅 목록 실시간 갱신)
        if created:
            try:
                from config.apps.chat_app.notifications import push_to_users
                from config.apps.notification.models import Notification
                title = room.title
                body = f"{instructor.user.username} 선생님이 과외를 제안했습니다."
                data = {"type": "new_room", "room_id": str(room.id)}
                Notification.objects.create(
                    user=post.student.user, type="new_room", title=title, body=body, data=data
                )
                push_to_users(
                    [post.student.user.id], title=title, body=body,
                    username=instructor.user.username, data=data
                )
            except Exception:
                pass  # FCM 실패는 무시

        return Response({
            "room_id": room.id,
            "instructor_id": instructor.id,
        }, status=status.HTTP_201_CREATED)


# ____________________________________________________________________________________
# 학생: 본인이 올린 과외 공고(TutoringPost)만 가볍게 조회하는 API
# ____________________________________________________________________________________

class StudentMyPostAPIView(generics.ListAPIView):
    """
    GET /tutoring/my-posts/
    학생이 본인이 올린 과외 공고를 조회합니다.
    - 리턴 필드: 공고의 과목(subjects), 조회수(view_count), 올린 지 며칠 지났는지(days_since_upload)
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentMyPostSerializer

    def get_queryset(self):
        from rest_framework.exceptions import PermissionDenied
        try:
            student = Student.objects.get(user=self.request.user)
        except Student.DoesNotExist:
            raise PermissionDenied("학생 계정만 사용할 수 있습니다.")
        
        # 본인이 작성한 활성화된/비활성화된 공고 모두 조회 (요구사항에 맞게 전체)
        return TutoringPost.objects.filter(student=student).order_by("-id")



# ____________________________________________________________________________________
# 수업 리소스 (TutoringResource) CRUD API
# ____________________________________________________________________________________
from django.db.models import Q
from .models import TutoringResource
from .serializers import TutoringResourceSerializer, TutoringResourceListSerializer

class IsResourceParticipant(permissions.BasePermission):
    """
    해당 수업 리소스의 과외 학생이거나 강사인 경우에만 접근 허용.
    """
    def has_object_permission(self, request, view, obj):
        return request.user == obj.student.user or request.user == obj.instructor.user

class TutoringResourceViewSet(ModelViewSet):
    """
    GET    /tutoring/resources/             수업 리소스 목록 조회 (본인이 포함된 것만)
    POST   /tutoring/resources/             수업 리소스 생성
    GET    /tutoring/resources/<pk>/        수업 리소스 상세 조회
    PATCH  /tutoring/resources/<pk>/        수업 리소스 수정 (학생/강사 확인 상태 등)
    DELETE /tutoring/resources/<pk>/        수업 리소스 삭제

    * 자신이 학생이든 강사든 참여하고 있는 리소스만 조회 가능합니다.

    Request (POST / PATCH):
    {
        "student": 9,
        "instructor": 12,
        "start_date": "2026-03-10",
        "class_type": "단기 수업",
        "subject": 4,
        "first_month_fee": 300000,
        "payback_bank": "국민은행",
        "payback_account_number": "123456-01-7890",
        "payback_account_holder": "홍길동",
        "is_student_confirmed": true,
        "is_instructor_confirmed": true
        // fee_confirmation_file의 경우 파일 업로드이므로 multipart/form-data로 전달
    }

    Response (POST/PATCH 200/201):
    {
        "id": 1,                             // int
        "student": 9,                        // int
        "instructor": 12,                    // int
        "start_date": "2026-03-10",          // date string (nullable)
        "class_type": "단기 수업",              // string (nullable)
        "subject": 4,                        // int (nullable)
        "first_month_fee": 300000,           // int (nullable)
        ...
        "is_student_confirmed": true,        // boolean
        "is_instructor_confirmed": true      // boolean
    }
    """
    permission_classes = [permissions.IsAuthenticated, IsResourceParticipant]
    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return TutoringResourceListSerializer
        return TutoringResourceSerializer

    def get_queryset(self):
        user = self.request.user
        qs = TutoringResource.objects.all()

        if self.action == 'list':
            # 자신이 참여하는 수업 리소스만 조회 가능하도록 제한
            return qs.filter(Q(student__user=user) | Q(instructor__user=user))
        
        # detail(retrieve/update/destroy) 액션의 경우 모든 queryset을 반환하고
        # 권한(Permission) 클래스에서 접근을 제어하여 404가 아닌 403을 반환하도록 설정
        return qs



# ____________________________________________________________________________________
# 과외 제안서 (TutoringProposal) — ViewSet
# ____________________________________________________________________________________
from .models import TutoringProposal
from django.db.models import Q
from .serializers import TutoringProposalSerializer

class TutoringProposalViewSet(mixins.CreateModelMixin,
                              mixins.UpdateModelMixin,
                              mixins.DestroyModelMixin,
                              mixins.ListModelMixin,
                              mixins.RetrieveModelMixin,
                              GenericViewSet):
    """
    제안서 CRUD (ModelViewSet과 동일한 mixin 구성)
    GET /tutoring/proposals/   : 제안서 목록
    POST /tutoring/proposals/  : 제안서 생성
    GET /tutoring/proposals/<pk>/ : 상세 조회
    PATCH /tutoring/proposals/<pk>/ : 수정
    DELETE /tutoring/proposals/<pk>/ : 삭제

    Request (POST / PATCH):
    {
        "tutoring_post": 101,          // int (required)
        "message": "제안합니다"             // string (optional, nullable)
    }

    Response (200/201):
    {
        "id": 10,                      // int
        "tutoring_post": 101,          // int
        "instructor": 5,               // int
        "message": "제안합니다",            // string (nullable)
        "created_at": "2026-03-04T12:00:00Z" // date string
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringProposalSerializer

    def get_queryset(self):
        user = self.request.user
        qs = TutoringProposal.objects.all().select_related("instructor", "tutoring_post__student")
        
        # 자신이 속한 제안서 (강사라면 자기가 보낸 것, 학생이라면 자기 공고에 달린 것)
        return qs.filter(Q(instructor__user=user) | Q(tutoring_post__student__user=user))

    def perform_create(self, serializer):
        instructor = get_object_or_404(Instructor, user=self.request.user)
        serializer.save(instructor=instructor)


# ____________________________________________________________________________________
# 강사 좋아요 (InstructorLike) — 학생이 강사를 좋아요/취소
# ____________________________________________________________________________________

from config.apps.accounts.models import InstructorLike

class InstructorLikeAPIView(APIView):
    """
    POST   /tutoring/instructors/<int:instructor_id>/like/    강사 좋아요
    DELETE /tutoring/instructors/<int:instructor_id>/like/    강사 좋아요 취소

    Path Params:
    - instructor_id: Instructor id

    Example Request (POST):
    - POST /tutoring/instructors/12/like/

    Example Response (POST 201):
    { "detail": "좋아요 완료" }

    Example Response (DELETE 204):
    (빈 응답)

    Example Response (POST 409 - 이미 좋아요):
    { "detail": "이미 좋아요한 강사입니다." }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, instructor_id):
        try:
            student = Student.objects.get(user=request.user)
        except Student.DoesNotExist:
            return Response({"detail": "학생 계정만 좋아요할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        instructor = get_object_or_404(Instructor, id=instructor_id)

        _, created = InstructorLike.objects.get_or_create(student=student, instructor=instructor)
        if not created:
            return Response({"detail": "이미 좋아요한 강사입니다."}, status=status.HTTP_409_CONFLICT)

        return Response({"detail": "좋아요 완료"}, status=status.HTTP_201_CREATED)

    def delete(self, request, instructor_id):
        try:
            student = Student.objects.get(user=request.user)
        except Student.DoesNotExist:
            return Response({"detail": "학생 계정만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        instructor = get_object_or_404(Instructor, id=instructor_id)

        deleted, _ = InstructorLike.objects.filter(student=student, instructor=instructor).delete()
        if not deleted:
            return Response({"detail": "좋아요한 적이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_204_NO_CONTENT)


# ____________________________________________________________________________________
# 공고 좋아요 (TutoringPostLike) — 강사가 공고를 좋아요/취소 (현재 삭제된 기능)
# ____________________________________________________________________________________

from .models import TutoringPostLike

class TutoringPostLikeAPIView(APIView):
    """
    POST   /tutoring/posts/<int:post_id>/like/    공고 좋아요
    DELETE /tutoring/posts/<int:post_id>/like/    공고 좋아요 취소

    Path Params:
    - post_id: TutoringPost id

    Example Request (POST):
    - POST /tutoring/posts/101/like/

    Example Response (POST 201):
    { "detail": "좋아요 완료" }

    Example Response (DELETE 204):
    (빈 응답)

    Example Response (POST 409 - 이미 좋아요):
    { "detail": "이미 좋아요한 공고입니다." }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, post_id):
        try:
            instructor = Instructor.objects.get(user=request.user)
        except Instructor.DoesNotExist:
            return Response({"detail": "강사 계정만 좋아요할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(TutoringPost, id=post_id)

        _, created = TutoringPostLike.objects.get_or_create(instructor=instructor, tutoring_post=post)
        if not created:
            return Response({"detail": "이미 좋아요한 공고입니다."}, status=status.HTTP_409_CONFLICT)

        return Response({"detail": "좋아요 완료"}, status=status.HTTP_201_CREATED)

    def delete(self, request, post_id):
        try:
            instructor = Instructor.objects.get(user=request.user)
        except Instructor.DoesNotExist:
            return Response({"detail": "강사 계정만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(TutoringPost, id=post_id)

        deleted, _ = TutoringPostLike.objects.filter(instructor=instructor, tutoring_post=post).delete()
        if not deleted:
            return Response({"detail": "좋아요한 적이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_204_NO_CONTENT)
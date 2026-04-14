from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.generics import GenericAPIView
from .models import User
from config.apps.pending.models import PendingInstructor
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    StudentSignupSerializer,
    InstructorSignupSerializer,
    StudentUpdateSerializer,
    InstructorUpdateSerializer,
)


class StudentSignupAPIView(APIView):
    """
    POST /accounts/signup/student/
    - Content-Type: application/json

    example request body:
    {
        "email": "student@example.com",
        "password": "securepassword123",
        "first_name": "Chiwoo",
        "last_name": "Jeon",
        "user_name": "나는치우",
        "phone": "01012345678",
        
        "sex": "남성",
        "birth_date": "2004-01-01",
        "region": "서울|강남구",
        "studentsubject": [1, 3, 7]
    }

    response example:
    {
        "id": 12,                       // int
        "email": "student@example.com", // string
        "role": "STUDENT"               // string
    }

    PUT/PATCH /accounts/signup/student/
    - Authorization: Token <token>
    - Content-Type: application/json

    example request body (partial ok):
    {
        "user_name": "새닉네임",
        "region": "서울|마포구",
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "01012345678"
    }
    """

    def post(self, request):
        serializer = StudentSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        return Response(
            {"id": user.id, "email": user.email, "role": "STUDENT"},
            status=status.HTTP_201_CREATED,
        )

    def put(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = StudentUpdateSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {"id": user.id, "email": user.email, "role": "STUDENT"},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        return self.put(request)


class InstructorSignupAPIView(GenericAPIView):
    """
    POST /accounts/signup/instructor/
    - Content-Type: multipart/form-data
    - pending_file 업로드 필요

    example request body (multipart/form-data):
    {
        "email": "instructor@example.com",
        "password": "securepassword123",
        "first_name": "Jane",
        "last_name": "Smith",
        "user_name": "제인",
        "phone": "01099998888",

        "sex": "여성",
        "birth_date": "2000-02-02",
        "region": "서울|서초구",
        "instructorsubject": [1, 2, 8],
        "instruction": "수업 소개 텍스트",

        "university": "UNIST",
        "department": "CSE",
        "student_number": "2024",
        "pending_file": <FILE>
    }

    response example:
    {
        "id": 34,                          // int
        "email": "instructor@example.com", // string
        "role": "INSTRUCTOR",              // string
        "pending_status": "PENDING"        // string
    }

    PUT/PATCH /accounts/signup/instructor/
    - Authorization: Token <token>
    - Content-Type: application/json

    example request body (partial ok):
    {
        "sex": "여성",
        "birth_date": "2000-01-01",
        "region": "서울|성동구",
        "instructorsubject": [3, 4],
        "instruction": "업데이트된 소개"
    }
    """

    serializer_class = InstructorSignupSerializer
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = InstructorSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        pending = user.instructor_profile.pending_info

        return Response(
            {"id": user.id, "email": user.email, "role": "INSTRUCTOR", "pending_status": pending.status},
            status=status.HTTP_201_CREATED,
        )

    def put(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = InstructorUpdateSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        pending_status = None
        if hasattr(user, "instructor_profile") and hasattr(user.instructor_profile, "pending_info"):
            pending_status = user.instructor_profile.pending_info.status

        return Response(
            {"id": user.id, "email": user.email, "role": "INSTRUCTOR", "pending_status": pending_status},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        return self.put(request)


class LoginAPIView(APIView):
    """
    POST /accounts/login/
    - Content-Type: application/json

    example request body:
    {
        "email": "student@example.com",
        "password": "securepassword123"
    }

    response example (success):
    {
        "token": "abc123...",            // string
        "user_id": 12,                   // int
        "email": "student@example.com",   // string
        "available_roles: [
            {
            "role": "student",
            "status": "VERIFIED"
            },
            {
            "role": "instructor",
            "status": "PENDING or SUSPENDED or VERIFIED"
            }
        ]
    }

    response example (instructor pending):
    {
        "error": "Account is pending verification" // string
    }
    """

    def post(self, request):
        password = request.data.get("password")
        email = request.data.get("email", "").lower()
        # email과 password는 필수
        if not email or not password:
            return Response({"error": "email/password required"}, status=400)
        # 이메일로 로그인 시도
        user = authenticate(request, username=email, password=password)
        if not user:
            return Response({"error": "Invalid credentials"}, status=400)
        
        # student/instructor 계정 상태 확인
        available_roles = []

        # 학생 계정이 있을 경우 role에 추가
        if hasattr(user, "student_profile"): 
            available_roles.append({"role": "student", "status": "VERIFIED"})

        if hasattr(user, "instructor_profile"): # 강사 계정이 있을 경우 role에 추가
            pending_status = user.instructor_profile.pending_info.status
            available_roles.append({"role": "instructor", "status": pending_status})

        if not available_roles: # 학생/강사 둘 다 없는 경우 error 반환(계정이 존재하지 않는 경우)
            return Response({"error": "No active roles found for this account"}, status=403)
        
        # 로그인 토큰 발급
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "token": token.key,
            "user_id": user.id,
            "email": user.email,
            "available_roles": available_roles
        }, status=200)

# 닉네임 중복 확인 API  
class CheckUsernameAPIView(APIView):
    """
    GET /accounts/check-username/?user_name=닉네임
    - Content-Type: application/json

    response example:
    {
        "available": true or false(미중복 or 중복) // boolean
    }
    """

    permission_classes = [] # 인증 없이 접근 가능

    def get(self, request):
        user_name = request.query_params.get("user_name", "")
        if not user_name:
            return Response({"error": "user_name query parameter required"}, status=400)

        # 현재 로그인한 사용자가 있는 경우, 그 사용자의 닉네임은 유효하다고 간주
        current_user_id = None
        if request.user and request.user.is_authenticated:
            current_user_id = request.user.id

        queryset = User.objects.filter(user_name__iexact=user_name)
        if current_user_id: # 로그인한 사용자가 있다면, 그 사용자의 닉네임은 중복 체크에서 제외(프로필 업데이트 시)
            queryset = queryset.exclude(pk=current_user_id)
        # 존재하지 않는 닉네임이면 available=True, 이미 존재하는 닉네임이면 available=False 반환
        available = not queryset.exists()
        return Response({"available": available}, status=200)

# 로그아웃 API  
class LogoutAPIView(APIView):
    """
    POST /accounts/logout/
    - Authorization: Token <token>
    """
    # 로그인한 유저만 호출 가능
    permission_classes = [IsAuthenticated]

    def post(self, request): 
        try:
            request.user.auth_token.delete() # 토큰 삭제로 로그아웃 처리
            return Response({"message": "Logged out successfully"}, status=200)
        except: # 토큰 삭제 실패 시 exception 처리 (예: 토큰이 이미 삭제된 경우)
            return Response({"error": "Failed to log out"}, status=400)

# 회원 탈퇴 API Soft Delete 방식 (데이터는 사내 정책에 따라 일정 기간 남기고, 일단 비활성화, 일정기간 후에 완전 삭제)
class WithdrawAPIView(APIView):
    """
    POST /accounts/withdraw/
    - Authorization: Token <token>
    """

    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        # 계정 비활성화
        user.is_active = False # 계정 비활성화
        user.save()
        # 토큰 삭제로 로그아웃 처리
        try:
            user.auth_token.delete()
        except Token.DoesNotExist:
            pass
        return Response({"message": "Account deactivated successfully"}, status=200)


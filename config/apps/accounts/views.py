from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.generics import GenericAPIView

from config.apps.pending.models import PendingInstructor
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
    POST /accounts/login/?type=student
    POST /accounts/login/?type=instructor
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
        "email": "student@example.com"   // string
    }

    response example (instructor pending):
    {
        "error": "Account is pending verification" // string
    }
    """

    def post(self, request):
        password = request.data.get("password")
        email = request.data.get("email", "").lower()

        if not email or not password:
            return Response({"error": "email/password required"}, status=400)

        user = authenticate(request, username=email, password=password)
        if not user:
            return Response({"error": "Invalid credentials"}, status=400)

        user_type = request.query_params.get("type")
        if user_type not in {"student", "instructor"}:
            return Response({"error": "type must be 'student' or 'instructor'"}, status=400)

        if user_type == "student":
            if not hasattr(user, "student_profile"):
                return Response({"error": "Not a student account"}, status=400)

            token = Token.objects.get_or_create(user=user)[0]
            return Response({"token": token.key, "user_id": user.id, "email": user.email})

        if not hasattr(user, "instructor_profile"):
            return Response({"error": "Not an instructor account"}, status=400)

        pending_status = user.instructor_profile.pending_info.status
        if pending_status == PendingInstructor.Status.VERIFIED:
            token = Token.objects.get_or_create(user=user)[0]
            return Response({"token": token.key, "user_id": user.id, "email": user.email})

        if pending_status == PendingInstructor.Status.SUSPENDED:
            return Response({"error": "Account is suspended"}, status=403)

        return Response({"error": "Account is pending verification"}, status=403)
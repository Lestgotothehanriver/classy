from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from config.throttles import LoginRateThrottle, SMSRateThrottle
from django.utils import timezone
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import GenericAPIView
from .models import User
from config.apps.pending.models import PendingInstructor
from django.shortcuts import get_object_or_404
from django.conf import settings
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    StudentSignupSerializer,
    InstructorSignupSerializer,
    StudentUpdateSerializer,
    InstructorUpdateSerializer,
    StudentRoleAddSerializer,
    InstructorRoleAddSerializer,
)
import logging
import random
from datetime import timedelta

# 전화번호 인증번호(OTP) 유효 시간
PHONE_VERIFICATION_EXPIRY = timedelta(minutes=3)
from solapi import SolapiMessageService
from solapi.model import RequestMessage

logger = logging.getLogger(__name__)


class PolicyVersionAPIView(APIView):
    """
    URL: /accounts/policy-version/

    약관/개인정보 현재 정책 버전(시행일)을 반환한다. 앱이 버전을 하드코딩하지 않고
    이 값을 표시/기록에 사용하며, 향후 재동의 판정의 기준이 된다. 인증 불필요.

    Returns:
        Response: {"terms": "2026-01-01", "privacy": "2026-01-01"}
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(getattr(settings, "POLICY_VERSIONS", {}), status=status.HTTP_200_OK)


class StudentSignupAPIView(APIView):
    """
    URL: /accounts/signup/student/

    학생용 회원가입 및 프로필 관리를 처리하는 API View입니다.

    POST 요청 시 신규 학생 유저의 회원가입을 처리하고 자동 로그인 인증 토큰 및 역할 정보를 발급합니다.
    PUT/PATCH 요청 시 로그인한 학생 유저의 프로필 정보를 부분 수정합니다.

    Request Body (POST):
        email (str): 이메일 주소.
        password (str): 비밀번호.
        user_name (str): 사용자 닉네임.
        phone (str): 전화번호.
        studentsubject (list[int], optional): 관심 과목 ID 리스트.

    Request Body (PUT/PATCH):
        user_name (str, optional): 변경할 닉네임.
        phone (str, optional): 변경할 전화번호.
        region (str, optional): 변경할 지역.

    Returns:
        Response (POST): {
            "token": str,
            "user_id": int,
            "email": str,
            "available_roles": List[dict],
            "message": "Signup successful"
        } (HTTP 201 Created)
        Response (PUT/PATCH): {
            "id": int,
            "email": str,
            "role": "STUDENT"
        }
    """

    def post(self, request):
        logger.debug("[BACKEND_DEBUG_AUTH] StudentSignup - START (data: %s)", request.data)
        serializer = StudentSignupSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            logger.warning(f"*** [StudentSignup] Validation failed: {serializer.errors} ***")
            serializer.is_valid(raise_exception=True)
            
        user = serializer.save()
        logger.info(f"*** [StudentSignup] User created successfully: {user.email} (ID: {user.id}) ***")

        # 회원가입 직후 자동 로그인용 토큰 발급
        token, _ = Token.objects.get_or_create(user=user)
        # 회원가입 직후 last_login 업데이트
        now = timezone.now()
        user.student_profile.last_login = now
        user.student_profile.save(update_fields=["last_login"])

        response_data = {
            "token": token.key,
            "user_id": user.id,
            "email": user.email,
            "available_roles": [
                {
                    "role": "student",
                    "status": "VERIFIED",
                    "last_login": user.student_profile.last_login.isoformat(),  # 최초 가입 시 회원가입 시간으로 last_login 업데이트
                }
            ],
        }
        logger.debug("[BACKEND_DEBUG_AUTH] SocialSignUp - SUCCESS (user: %s)", user.pk)
        return Response(
            {**response_data, "message": "Signup successful"},
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
    URL: /accounts/signup/instructor/

    강사 회원가입 및 프로필 업데이트를 처리하는 API View입니다.

    POST 요청 시 강사 회원가입 처리를 진행하며 학력/경력 인증을 위한 서류 파일(pending_file)을 함께 제출받아 PENDING 상태로 심사 요청을 등록합니다.
    PUT/PATCH 요청 시 로그인한 강사 유저의 소속 및 정보 프로필을 부분 수정합니다.

    Request Body (POST, Multipart):
        email (str): 이메일 주소.
        password (str): 비밀번호.
        user_name (str): 사용자 닉네임.
        phone (str): 전화번호.
        university (str): 소속 대학교명.
        department (str, optional): 소속 학과명.
        pending_file (File): 인증 서류 이미지 또는 PDF 파일.

    Request Body (PUT/PATCH):
        university (str, optional): 대학교명.
        department (str, optional): 학과명.

    Returns:
        Response (POST): {
            "id": int,
            "email": str,
            "role": "INSTRUCTOR",
            "pending_status": str,
            "token": str
        } (HTTP 201 Created)
        Response (PUT/PATCH): {
            "id": int,
            "email": str,
            "role": "INSTRUCTOR",
            "pending_status": str
        }
    """

    serializer_class = InstructorSignupSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        logger.debug("[BACKEND_DEBUG_AUTH] InstructorSignup - email: %s", request.data.get('email'))
        serializer = InstructorSignupSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            logger.warning(f"*** [InstructorSignup] Validation failed: {serializer.errors} ***")
            serializer.is_valid(raise_exception=True)
            
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        now = timezone.now()
        user.instructor_profile.last_login = now
        user.instructor_profile.save(update_fields=["last_login"])
        logger.info(f"*** [InstructorSignup] Instructor user created: {user.email} (ID: {user.id}) ***")

        pending = getattr(user.instructor_profile, 'pending_info', None)
        pending_status = pending.status if pending else 'NOT_SUBMITTED'

        return Response(
            {"id": user.id, "email": user.email, "role": "INSTRUCTOR", "pending_status": pending_status, "token": token.key},
            status=status.HTTP_201_CREATED,
        )

    def put(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = InstructorUpdateSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        pending_status = None
        if hasattr(user, "instructor_profile"):
            pending = getattr(user.instructor_profile, 'pending_info', None)
            pending_status = pending.status if pending else 'NOT_SUBMITTED'

        return Response(
            {"id": user.id, "email": user.email, "role": "INSTRUCTOR", "pending_status": pending_status},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        return self.put(request)


class LoginAPIView(APIView):
    """
    URL: /accounts/login/

    이메일과 비밀번호를 사용하여 인증(Login) 토큰을 발급하는 API View입니다.

    POST 요청 시 입력된 이메일과 비밀번호로 계정을 인증하고 토큰을 반환합니다.
    학생 계정은 즉시 로그인 및 사용이 가능하며, 강사 계정인 경우 심사가 거류(PENDING) 또는 정지(SUSPENDED)된 상태라면 로그인이 제한될 수 있으며 해당 유저의 모든 활성 역할(student, instructor) 정보를 함께 구성하여 응답합니다.

    Request Body:
        email (str): 이메일 주소.
        password (str): 비밀번호.

    Returns:
        Response: {
            "token": str,
            "user_id": int,
            "email": str,
            "available_roles": List[dict]
        }
    """
    parser_classes = [JSONParser]  # JSON(앱) + multipart(테스트 등) 모두 허용
    permission_classes = []
    throttle_classes = [LoginRateThrottle]
    
    def post(self, request):
        logger.info("[BACKEND_DEBUG_AUTH] Login - START (email: %s)", request.data.get('email'))
        password = request.data.get("password")
        email = request.data.get("email", "").strip().lower()
        logger.info("[BACKEND_DEBUG_AUTH] Login Attempt - email: %s", email)
        
        # email과 password는 필수
        if not email or not password:
            logger.warning("*** [Login] Missing email or password ***")
            return Response({"error": "email/password required"}, status=400)
            
        # 이메일로 로그인 시도
        user = authenticate(request, username=email, password=password)
        if not user:
            logger.warning("[BACKEND_DEBUG_AUTH] Login FAILED (Invalid credentials) - email: %s", email)
            return Response({"error": "Invalid credentials"}, status=400)
        
        logger.debug("[BACKEND_DEBUG_AUTH] Login SUCCESS - email: %s", user.email)
        
        # student/instructor 계정 상태 확인
        available_roles = []
        now = timezone.now()

        # 학생 계정이 있을 경우 role에 추가
        if hasattr(user, "student_profile"):
            student = user.student_profile
            prev_last_login = student.last_login
            student.last_login = now
            student.save(update_fields=["last_login"])
            available_roles.append({
                "role": "student",
                "status": "VERIFIED",
                "last_login": prev_last_login.isoformat() if prev_last_login else None,
            })

        if hasattr(user, "instructor_profile"):
            instructor = user.instructor_profile
            pending_info = getattr(instructor, 'pending_info', None)
            pending_status = pending_info.status if pending_info else 'NOT_SUBMITTED'
            prev_last_login = instructor.last_login
            instructor.last_login = now
            instructor.save(update_fields=["last_login"])
            available_roles.append({
                "role": "instructor",
                "status": pending_status,
                "last_login": prev_last_login.isoformat() if prev_last_login else None,
            })

        # 로그인 토큰 발급
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "token": token.key,
            "user_id": user.id,
            "email": user.email,
            "available_roles": available_roles,
        }, status=200)

# 닉네임 중복 확인 API  
class CheckUsernameAPIView(APIView):
    """
    URL: /accounts/check-username/

    닉네임(user_name)의 중복 여부를 검사하는 API View입니다.

    GET 요청 시 쿼리 파라미터로 전달된 user_name의 중복 여부를 조회합니다.
    인증된 유저가 프로필 수정 중에 요청하는 경우에는 본인의 현재 닉네임은 중복 검사에서 제외합니다.

    Query Parameters:
        user_name (str): 중복 여부를 검사할 닉네임.

    Returns:
        Response: {
            "available": bool
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

# 이메일 중복 확인 API  
class CheckEmailAPIView(APIView):
    """
    URL: /accounts/check-email/

    이메일(email)의 중복 여부를 검사하는 API View입니다.

    GET 요청 시 쿼리 파라미터로 전달된 이메일의 중복 여부를 조회합니다.
    인증된 유저가 프로필 수정 중에 요청하는 경우에는 본인의 현재 이메일은 중복 검사에서 제외합니다.

    Query Parameters:
        email (str): 중복 여부를 검사할 이메일 주소.

    Returns:
        Response: {
            "available": bool
        }
    """

    permission_classes = [] # 인증 없이 접근 가능

    def get(self, request):
        email = request.query_params.get("email", "")
        if not email:
            return Response({"error": "email query parameter required"}, status=400)

        # 현재 로그인한 사용자가 있는 경우, 그 사용자의 이메일은 유효하다고 간주
        current_user_id = None
        if request.user and request.user.is_authenticated:
            current_user_id = request.user.id

        queryset = User.objects.filter(email__iexact=email)
        if current_user_id: # 로그인한 사용자가 있다면, 그 사용자의 이메일은 중복 체크에서 제외(프로필 업데이트 시)
            queryset = queryset.exclude(pk=current_user_id)
        # 존재하지 않는 이메일이면 available=True, 이미 존재하는 이메일이면 available=False 반환
        available = not queryset.exists()
        return Response({"available": available}, status=200)

# 로그아웃 API  
class LogoutAPIView(APIView):
    """
    URL: /accounts/logout/

    사용자 로그아웃 및 인증 토큰을 파기하는 API View입니다.

    POST 요청 시, 요청 유저의 DeviceToken을 비활성화(is_active=False)하여 알림 수신을 차단하고, DB에 저장된 Django REST Framework 인증 토큰을 즉시 파기(삭제)합니다.

    Returns:
        Response: {
            "message": "Logged out successfully"
        }
    """
    # 로그인한 유저만 호출 가능
    permission_classes = [IsAuthenticated]

    def post(self, request): 
        try:
            # FCM 토큰 비활성화 (로그아웃 후 푸시 알림 차단)
            from config.apps.notification.models import DeviceToken
            DeviceToken.objects.filter(user=request.user).update(is_active=False)
        except Exception as e:
            logger.warning(f"*** [Logout] FCM token deactivation failed: {e} ***")
        try:
            request.user.auth_token.delete()  # 인증 토큰 삭제
            return Response({"message": "Logged out successfully"}, status=200)
        except:
            return Response({"error": "Failed to log out"}, status=400)

# 회원 탈퇴 API Soft Delete 방식 (데이터는 사내 정책에 따라 일정 기간 남기고, 일단 비활성화, 일정기간 후에 완전 삭제)
class WithdrawAPIView(APIView):
    """
    URL: /accounts/withdraw/

    회원 탈퇴(Soft Delete)를 처리하는 API View입니다.

    POST 요청 시 탈퇴 사유(reason, reason_detail)를 저장하고 계정 상태를 비활성화(is_active=False) 처리하며, FCM 디바이스 토큰 및 사용자의 인증 토큰을 파기합니다.

    Request Body:
        reason (str, optional): 탈퇴 사유.
        reason_detail (str, optional): 탈퇴 상세 내용.

    Returns:
        Response: {
            "message": "Account deactivated successfully"
        }
    """

    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        # 탈퇴 사유 저장
        reason = request.data.get('reason', '')
        reason_detail = request.data.get('reason_detail', '')
        user.withdraw_reason = reason
        user.withdraw_reason_detail = reason_detail
        # 계정 비활성화
        user.is_active = False
        user.save(update_fields=['is_active', 'withdraw_reason', 'withdraw_reason_detail'])
        # FCM 토큰 비활성화
        try:
            from config.apps.notification.models import DeviceToken
            DeviceToken.objects.filter(user=user).update(is_active=False)
        except Exception as e:
            logger.warning(f"*** [Withdraw] FCM token deactivation failed: {e} ***")
        # 인증 토큰 삭제
        try:
            user.auth_token.delete()
        except Token.DoesNotExist:
            pass
        return Response({"message": "Account deactivated successfully"}, status=200)


class CheckPhoneAPIView(APIView):
    """
    URL: /accounts/check-phone/

    입력된 휴대전화 번호로 가입된 계정 존재 여부 및 역할을 검사하는 API View입니다.

    GET 요청 시, 전달받은 번호로 가입된 User가 없으면 exists: false를 반환합니다.
    가입된 계정이 존재하는 경우, 정지(Banned) 및 탈퇴(Inactive) 계정 여부를 확인하고, 학생/강사 역할이 둘 다 있는지 한쪽 역할만 있는지에 따라 missing_role 또는 role_full 여부를 계산하여 응답합니다.

    Query Parameters:
        phone (str): 검사할 휴대전화 번호.

    Returns:
        Response: {
            "exists": bool,
            "email": str (존재 시),
            "is_banned": bool (정지된 경우),
            "is_inactive": bool (탈퇴한 경우),
            "missing_role": "student" | "instructor",
            "role_full": bool
        }
    """
    permission_classes = []

    def get(self, request):
        phone = request.query_params.get('phone', '').strip()
        if not phone:
            return Response({"error": "phone query parameter required"}, status=400)

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response({"exists": False}, status=200)

        # 기본 응답 데이터
        response_data = {
            "exists": True,
            "email": user.email,
        }

        # 밴 계정 체크
        if user.is_banned:
            response_data["is_banned"] = True
            return Response(response_data, status=200)

        # 비활성화(탈퇴) 계정 체크
        if not user.is_active:
            response_data["is_inactive"] = True
            return Response(response_data, status=200)

        has_student = hasattr(user, 'student_profile')
        has_instructor = hasattr(user, 'instructor_profile')

        if has_student and has_instructor:
            return Response({"exists": True, "role_full": True}, status=200)
        elif has_student:
            return Response({"exists": True, "missing_role": "instructor"}, status=200)
        else:
            return Response({"exists": True, "missing_role": "student"}, status=200)


class AddRoleAPIView(APIView):
    """
    URL: /accounts/add-role/

    기존 가입 계정에 새로운 역할(student 또는 instructor)을 추가 등록하는 API View입니다.

    POST 요청 시 휴대전화 번호와 비밀번호를 통해 인증을 진행한 후, 아직 보유하지 않은 역할의 프로필을 생성합니다.
    학생 역할을 추가할 때에는 관심 과목 목록(studentsubject)을 처리하며, 강사 역할을 추가할 때에는 대학 정보(university, department)를 등록받고 자격 증명 심사 상태를 생성합니다.

    Request Body (Multipart):
        phone (str): 인증할 전화번호.
        password (str): 인증할 비밀번호.
        role (str): 추가할 역할 ('student' | 'instructor').
        studentsubject (list[int] 또는 str, optional): 학생 역할 추가 시 관심 과목 번호 목록.
        university (str, optional): 강사 역할 추가 시 대학교명 (필수).
        department (str, optional): 강사 역할 추가 시 학과명.

    Returns:
        Response: {
            "token": str,
            "user_id": int,
            "email": str,
            "available_roles": List[dict]
        } (HTTP 201 Created)
    """
    permission_classes = []
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        password = request.data.get('password', '')
        role = request.data.get('role', '')

        if not all([phone, password, role]):
            return Response({"error": "phone, password, role 필드가 필요합니다."}, status=400)

        if role not in ['student', 'instructor']:
            return Response({"error": "role은 student 또는 instructor이어야 합니다."}, status=400)

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response({"error": "해당 번호로 가입된 계정이 없습니다."}, status=404)

        # 비밀번호 확인
        if not user.check_password(password):
            return Response({"error": "비밀번호가 올바르지 않습니다."}, status=400)

        if user.is_banned:
            return Response({"error": "서비스 이용이 정지된 계정입니다."}, status=403)

        if role == 'student':
            if hasattr(user, 'student_profile'):
                return Response({"error": "이미 학생 계정이 존재합니다."}, status=400)
            from config.apps.accounts.models import Student
            student = Student.objects.create(user=user)
            subjects = request.data.get('studentsubject', [])
            if isinstance(subjects, str):
                import json
                try:
                    subjects = json.loads(subjects)
                except Exception:
                    subjects = []
            if subjects:
                from config.apps.accounts.models import Subject
                student.subjects.set(Subject.objects.filter(number__in=subjects))
                student.save()
        elif role == 'instructor':
            if hasattr(user, 'instructor_profile'):
                return Response({"error": "이미 강사 계정이 존재합니다."}, status=400)
            from config.apps.accounts.serializers import InstructorSignupSerializer
            # 기존 InstructorSignupSerializer에서 user 생성 부분만 스킵
            # 최소 필드: university 필수
            university = request.data.get('university', '')
            department = request.data.get('department', '')
            if not university:
                return Response({"error": "university 필드가 필요합니다."}, status=400)
            from config.apps.accounts.models import Instructor
            instructor = Instructor.objects.create(
                user=user,
                university=university,
                department=department,
            )
            # 서류 파일 제출은 마이페이지로 일원화됨
            from config.apps.pending.models import PendingInstructor
            pending, _ = PendingInstructor.objects.get_or_create(
                instructor_profile=instructor,
                defaults={'status': PendingInstructor.Status.PENDING}
            )

        token, _ = Token.objects.get_or_create(user=user)
        available_roles = []
        if hasattr(user, 'student_profile'):
            available_roles.append({"role": "student", "status": "VERIFIED"})
        if hasattr(user, 'instructor_profile'):
            pi = getattr(user.instructor_profile, 'pending_info', None)
            available_roles.append({
                "role": "instructor",
                "status": pi.status if pi else "PENDING"
            })

        return Response({
            "token": token.key,
            "user_id": user.id,
            "email": user.email,
            "available_roles": available_roles,
        }, status=201)


class UserProfileAPIView(APIView):
    """
    URL: /accounts/me/

    본인의 프로필 조회 및 수정을 처리하는 API View입니다.

    GET 요청 시 로그인한 유저 본인의 닉네임, 이름, 캐시 잔액, 프로필 이미지 주소, 거주 지역 정보 및 번호 정보를 반환합니다.
    PATCH 요청 시 닉네임, 전화번호, 지역, 분야(field) 정보를 부분 변경합니다. 닉네임 수정 시 중복 검사를 거칩니다.

    Request Body (PATCH):
        user_name (str, optional): 수정할 닉네임.
        phone (str, optional): 수정할 전화번호.
        region (str, optional): 수정할 지역 정보 ('시|구' 포맷).
        field (str, optional): 수정할 분야 정보.

    Returns:
        Response (GET): {
            "nickname": str,
            "last_name": str,
            "first_name": str,
            "cash": int,
            "profile_image": str,
            "district": str,
            "province": str,
            "phonenumber": str
        }
        Response (PATCH): {
            "id": int,
            "email": str,
            "nickname": str,
            "phone": str,
            "field": str,
            "province": str,
            "district": str,
            "profile_image": str
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        logger.info(f"*** [UserProfile] Fetch profile for: {user.email} ***")
        region_parts = user.region.split(' ') if user.region else ['', '']

        data = {
            "id": user.id,
            "email": user.email,
            "nickname": user.user_name,
            "last_name": user.last_name,
            "first_name": user.first_name,
            "role": "instructor" if hasattr(user, "instructor_profile") else "student",
            "cash": user.cash,
            "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
            "region": user.region,
            "district": region_parts[1] if len(region_parts) > 1 else "",
            "province": region_parts[0] if len(region_parts) > 0 else "",
            "sex": user.sex,
            "birth_date": str(user.birth_date) if user.birth_date else None,
            "field": user.field,
            "phonenumber": user.phone,
        }

        if hasattr(user, "instructor_profile"):
            instructor = user.instructor_profile
            data.update({
                "university": instructor.university,
                "department": instructor.department,
                "student_number": instructor.student_number,
                "instruction": instructor.instruction,
                "subjects": [str(subject) for subject in instructor.subjects.all()],
            })
        elif hasattr(user, "student_profile"):
            data["subjects"] = [
                str(subject) for subject in user.student_profile.subjects.all()
            ]

        return Response(data)

    def patch(self, request):
        user = request.user
        data = request.data

        if 'user_name' in data:
            new_name = data['user_name']
            if User.objects.exclude(pk=user.pk).filter(user_name__iexact=new_name).exists():
                return Response({"error": "이미 사용 중인 닉네임입니다."}, status=400)
            user.user_name = new_name

        if 'phone' in data:
            user.phone = data['phone']

        if 'region' in data:
            user.region = data['region']

        if 'field' in data:
            user.field = data['field']

        patchable = ['user_name', 'phone', 'region', 'field']
        update_fields = [f for f in patchable if f in data]
        if update_fields:
            user.save(update_fields=update_fields)

        region_parts = user.region.split('|') if user.region else ["", ""]
        return Response({
            "id": user.id,
            "email": user.email,
            "nickname": user.user_name,
            "phone": user.phone,
            "field": user.field,
            "province": region_parts[0] if len(region_parts) > 0 else "",
            "district": region_parts[1] if len(region_parts) > 1 else "",
            "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
        })


class RequestPhoneChangeAPIView(APIView):
    """
    URL: /accounts/me/phone/request/

    전화번호 변경을 위한 SMS 인증번호 발송을 요청하는 API View입니다.

    POST 요청 시, 변경할 신규 전화번호를 입력받아 이미 다른 계정에서 가입된 번호가 아닌지 중복을 검사하고, 6자리 난수의 인증 코드를 생성하여 PhoneVerification 내역에 기록합니다. 개발 편의를 위해 생성된 코드가 응답에 반환됩니다.

    Request Body:
        phone (str): 변경할 전화번호.

    Returns:
        Response: {
            "message": "인증번호가 발송되었습니다.",
            "code": str
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        if not phone:
            return Response({"error": "전화번호가 필요합니다."}, status=400)
            
        # 중복 체크
        if User.objects.filter(phone=phone).exclude(pk=request.user.pk).exists():
            return Response({"error": "이미 사용 중인 전화번호입니다."}, status=400)

        # 6자리 인증번호 생성
        code = str(random.randint(100000, 999999))
        
        from .models import PhoneVerification
        PhoneVerification.objects.create(
            user=request.user,
            phone=phone,
            code=code
        )
        
        # 실제 SMS 전송 로직이 들어갈 자리 (현재는 모킹)
        logger.info(f"*** [PhoneChange] Verification code for {phone}: {code} ***")
        
        # 개발 편의를 위해 응답에 코드를 포함 (운영 시에는 제거)
        return Response({
            "message": "인증번호가 발송되었습니다.",
            "code": code
        }, status=200)


class VerifyPhoneChangeAPIView(APIView):
    """
    URL: /accounts/me/phone/verify/

    발송된 인증번호를 대조하여 사용자의 휴대전화 번호를 최종 변경하는 API View입니다.

    POST 요청 시 신규 번호와 6자리 코드를 입력받아 PhoneVerification 테이블의 최근 미인증 데이터를 검증합니다.
    인증이 성공하면 해당 유저의 phone 값을 새 번호로 갱신하고 인증 완료 마킹을 진행합니다.

    Request Body:
        phone (str): 인증한 전화번호.
        code (str): 인증 코드.

    Returns:
        Response: {
            "message": "전화번호가 성공적으로 변경되었습니다.",
            "phone": str
        }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        code = request.data.get('code', '').strip()
        
        if not all([phone, code]):
            return Response({"error": "전화번호와 인증번호가 필요합니다."}, status=400)
            
        from .models import PhoneVerification
        # 1) 코드 일치 여부 먼저 확인 (시간 무관)
        verification = PhoneVerification.objects.filter(
            user=request.user,
            phone=phone,
            code=code,
            is_verified=False,
        ).order_by('-created_at').first()

        if not verification:
            return Response({"error": "인증번호가 올바르지 않습니다."}, status=400)

        # 2) 만료 여부 확인
        if verification.created_at < timezone.now() - PHONE_VERIFICATION_EXPIRY:
            return Response({"error": "인증번호가 만료되었습니다. 다시 요청해주세요."}, status=400)

        # 유저 전화번호 업데이트
        user = request.user
        user.phone = phone
        user.save(update_fields=['phone'])
        
        verification.is_verified = True
        verification.save(update_fields=['is_verified'])
        
        return Response({
            "message": "전화번호가 성공적으로 변경되었습니다.",
            "phone": user.phone
        }, status=200)


class ProfileImageAPIView(APIView):
    """
    URL: /accounts/me/image/

    로그인한 유저의 프로필 이미지 업로드 및 교체를 처리하는 API View입니다.

    PATCH 요청 시 업로드된 프로필 이미지 파일을 전달받아 사용자 계정의 profile_image 경로에 등록하고, 변경된 프로필 이미지의 절대 경로 URL을 반환합니다.

    Request Body (Multipart):
        profile_image (File): 업로드할 이미지 파일.

    Returns:
        Response: {
            "profile_image": str
        }
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request):
        if 'profile_image' not in request.FILES:
            return Response({"error": "profile_image 파일이 필요합니다."}, status=400)

        user = request.user
        user.profile_image = request.FILES['profile_image']
        user.save(update_fields=['profile_image'])

        return Response({
            "profile_image": request.build_absolute_uri(user.profile_image.url),
        }, status=200)

class InstructorRetryAPIView(APIView):
    """
    URL: /accounts/signup/instructor/retry/

    강사 승인 거절 상태에서 인증 서류를 보강하여 재인증을 요청하는 API View입니다.

    POST 요청 시, 이메일을 식별자로 하여 해당 강사의 심사 내역(PendingInstructor) 상태를 PENDING으로 재설정하고, 기존 업로드 파일을 삭제한 후 새 서류 파일(pending_file)로 교체합니다.
    선택적으로 소속 대학 및 학번 정보를 추가 보강하며, 푸시용 FCM 디바이스 토큰 정보를 함께 갱신 처리합니다.

    Request Body (Multipart):
        email (str): 강사 계정 이메일 주소.
        pending_file (File): 재심사용 인증 서류 파일.
        university (str, optional): 보강할 대학교명.
        department (str, optional): 보강할 학과명.
        student_number (str, optional): 보강할 학번.
        fcm_token (str, optional): 최신 FCM 디바이스 토큰.
        platform (str, optional): 디바이스 플랫폼 ('android' | 'ios' 등).

    Returns:
        Response: {
            "message": "재심사 요청이 성공적으로 접수되었습니다."
        }
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = []

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        logger.debug("[BACKEND_DEBUG_AUTH] InstructorRetry - email: %s, files: %s", email, request.FILES.keys())
        if not email:
            return Response({"error": "이메일이 필요합니다."}, status=400)
            
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"error": "가입되지 않은 이메일입니다."}, status=400)
            
        if not hasattr(user, 'instructor_profile') or not hasattr(user.instructor_profile, 'pending_info'):
            return Response({"error": "강사 프로필이 존재하지 않습니다."}, status=400)
            
        pending_info = user.instructor_profile.pending_info
        
        # 거절(SUSPENDED) 상태인 경우에만 재인증 허용
        if pending_info.status != PendingInstructor.Status.SUSPENDED:
            return Response({"error": "거절(보류)된 계정만 재심사를 요청할 수 있습니다."}, status=400)
            
        instructor_profile = user.instructor_profile
        
        # (선택) 정보 업데이트
        if 'university' in request.data:
            instructor_profile.university = request.data['university']
        if 'department' in request.data:
            instructor_profile.department = request.data['department']
        if 'student_number' in request.data:
            instructor_profile.student_number = request.data['student_number']
        instructor_profile.save()
        
        # 파일 업데이트
        if 'pending_file' in request.FILES:
            from config.apps.pending.models import File
            # 기존 파일 삭제 및 새로 등록
            File.objects.filter(pending_instructor=pending_info).delete()
            File.objects.create(pending_instructor=pending_info, pending_file=request.FILES['pending_file'])
            
        # 상태 PENDING으로 초기화
        pending_info.status = PendingInstructor.Status.PENDING
        pending_info.save()

        # FCM 디바이스 토큰 등록 (재인증 시점에 최신 토큰으로 갱신)
        fcm_token = request.data.get('fcm_token', '').strip()
        platform = request.data.get('platform', 'android')
        if fcm_token:
            from config.apps.notification.models import DeviceToken
            # 다른 유저가 동일 토큰을 가지고 있으면 제거 (기기 소유권 이전 대응)
            DeviceToken.objects.filter(token=fcm_token).exclude(user=user).delete()
            DeviceToken.objects.update_or_create(
                user=user,
                token=fcm_token,
                defaults={'platform': platform, 'is_active': True}
            )
            logger.info("[BACKEND_DEBUG_AUTH] Updated DeviceToken for %s", email)

        logger.debug("[BACKEND_DEBUG_AUTH] InstructorRetry SUCCESS - email: %s", email)
        
        return Response({"message": "재심사 요청이 성공적으로 접수되었습니다."}, status=200)


class UserDetailAPIView(APIView):
    """
    URL: /accounts/user/<pk>/

    지정한 특정 사용자의 공개 프로필 정보를 조회하는 API View입니다.

    GET 요청 시, 지정한 pk에 해당하는 유저의 닉네임, 역할군(student 또는 instructor), 활동 지역, 성별, 생년월일, 프로필 이미지 URL, 관심/지도 과목 리스트, 그리고 강사일 경우 서류 심사 인증 상태(certified, pending, rejected) 정보를 한 번에 결합하여 제공합니다.

    Path Parameters:
        pk (int): 정보를 조회할 대상 사용자(User) ID.

    Returns:
        Response: {
            "id": int,
            "email": str,
            "nickname": str,
            "first_name": str,
            "last_name": str,
            "role": "student" | "instructor",
            "region": str,
            "province": str,
            "district": str,
            "sex": str,
            "field": str,
            "birth_date": str,
            "profile_image": str,
            "verification_status": "certified" | "pending" | "rejected" | None,
            "subjects": List[str]
        }
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        
        is_instructor = hasattr(user, 'instructor_profile')
        role = 'instructor' if is_instructor else 'student'
        region_parts = user.region.split(' ') if user.region else ['', '']

        _STATUS_MAP = {'PENDING': 'pending', 'VERIFIED': 'certified', 'SUSPENDED': 'rejected'}
        verification_status = None
        subjects = []

        from config.apps.tutoring.constant import STUDENT_SUBJECT_CHOICES
        _choices_map = dict(STUDENT_SUBJECT_CHOICES)

        if is_instructor:
            pending_info = getattr(user.instructor_profile, 'pending_info', None)
            raw_status = pending_info.status if pending_info else 'PENDING'
            verification_status = _STATUS_MAP.get(raw_status, 'pending')
            subjects = [
                _choices_map.get(n, str(n))
                for n in user.instructor_profile.subjects.values_list('number', flat=True)
            ]
        else:
            subjects = [
                _choices_map.get(n, str(n))
                for n in user.student_profile.subjects.values_list('number', flat=True)
            ]

        return Response({
            "id": user.id,
            "email": user.email,
            "nickname": user.user_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": role,
            "region": user.region,
            "province": region_parts[0] if len(region_parts) > 0 else "",
            "district": region_parts[1] if len(region_parts) > 1 else "",
            "sex": user.sex,
            "field": user.field,
            "birth_date": str(user.birth_date) if user.birth_date else None,
            "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
            "verification_status": verification_status,
            "subjects": subjects,
        })
class SubjectListAPIView(APIView):
    """
    URL: /accounts/subjects/

    시스템 내 등록된 전체 과목(Subject) 목록을 조회하는 API View입니다.

    GET 요청 시, 데이터베이스에 등록된 모든 교과목 목록을 번호(number) 순으로 정렬하여 반환합니다.

    Returns:
        Response: List[SubjectSerializer] 데이터
    """
    permission_classes = []

    def get(self, request):
        from .models import Subject
        from .serializers import SubjectSerializer
        subjects = Subject.objects.all().order_by('number')
        serializer = SubjectSerializer(subjects, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

#_____________________________________________________________
# API 키와 API Secret을 설정.
message_service = SolapiMessageService(
    api_key=settings.SOLAPI_API_KEY, api_secret=settings.SOLAPI_API_SECRET
)

from_number = settings.SOLAPI_SENDER

def send_auth_sms(phone_number, auth_code):
    request = RequestMessage(
        to=phone_number,  # 수신 번호
        from_=from_number, # 발신 번호
        text=f"[Classy] 인증번호: {auth_code}",  # 문자 메시지 내용
    )
    try:
        response = message_service.send(request)
        logger.info(f"[SMS] Sent authentication code to {phone_number}: {response}")
        return True
    except Exception as e:
        failed_msgs = getattr(e, 'failed_messages', None)
        if failed_msgs:
            logger.error(f"[SMS] Failed to send authentication code to {phone_number}: {e} | Detailed failure: {failed_msgs}")
        else:
            logger.error(f"[SMS] Failed to send authentication code to {phone_number}: {e}")
        return False


class SendAuthSMSAPIView(APIView):
    """
    URL: /accounts/send-auth-sms/

    입력한 번호로 가입/본인인증을 위한 6자리 SMS 인증번호를 발송하는 API View입니다.

    POST 요청 시, 전달받은 번호로 솔라피(Solapi) 서비스를 호출하여 인증 문자를 발송하고, 생성된 코드를 PhoneVerification 테이블에 미인증 상태로 저장합니다. 개발용 편의를 위해 발송된 코드가 응답에 함께 반환됩니다.

    Request Body:
        phone_number (str): 문자를 수신할 휴대전화 번호.

    Returns:
        Response: {
            "message": "인증번호가 발송되었습니다.",
            "code": str
        }
    """
    permission_classes = []
    throttle_classes = [SMSRateThrottle]

    def post(self, request):
        phone_number = request.data.get('phone_number')
        if not phone_number:
            return Response({"error": "전화번호가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        auth_code = str(random.randint(100000, 999999))
        
        if not send_auth_sms(phone_number, auth_code):
            return Response({"error": "인증번호 발송에 실패했습니다. 발송 정보를 확인해 주세요."}, status=status.HTTP_400_BAD_REQUEST)
        
        from .models import PhoneVerification
        PhoneVerification.objects.create(
            user=request.user if request.user and request.user.is_authenticated else None,
            phone=phone_number,
            code=auth_code
        )
        
        return Response({
            "message": "인증번호가 발송되었습니다.",
            "code": auth_code
        }, status=status.HTTP_200_OK)


class VerifyAuthSMSAPIView(APIView):
    """
    URL: /accounts/verify-auth-sms/

    입력된 SMS 인증번호와 전화번호를 대조하여 인증을 완료 처리하는 API View입니다.

    POST 요청 시 휴대전화 번호와 수신한 6자리 인증 코드를 확인하여 데이터베이스에 저장된 내역을 대조합니다.
    검증에 성공하는 경우, 해당 인증 내역을 인증 완료(is_verified=True)로 업데이트합니다.

    Request Body:
        phone_number (str): 인증할 휴대전화 번호.
        code (str): 수신한 6자리 인증 번호.

    Returns:
        Response: {
            "message": "전화번호 인증이 완료되었습니다."
        }
    """
    permission_classes = []

    def post(self, request):
        phone_number = request.data.get('phone_number')
        code = request.data.get('code')
        
        if not all([phone_number, code]):
            return Response({"error": "전화번호와 인증번호가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
            
        from .models import PhoneVerification
        # 1) 코드 일치 여부 먼저 확인 (시간 무관)
        verification = PhoneVerification.objects.filter(
            phone=phone_number,
            code=code,
            is_verified=False,
        ).order_by('-created_at').first()

        if not verification:
            return Response({"error": "인증번호가 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 2) 만료 여부 확인
        if verification.created_at < timezone.now() - PHONE_VERIFICATION_EXPIRY:
            return Response({"error": "인증번호가 만료되었습니다. 다시 요청해주세요."}, status=status.HTTP_400_BAD_REQUEST)

        verification.is_verified = True
        verification.save(update_fields=['is_verified'])
        
        return Response({
            "message": "전화번호 인증이 완료되었습니다."
        }, status=status.HTTP_200_OK)


class ProfileCheckAPIView(APIView):
    """
    URL: /accounts/profile-check/

    현재 로그인 유저의 프로필 역할 정보 및 인증 토큰 상태를 조회하는 API View입니다.

    GET 요청 시, 로그인된 사용자의 학생 및 강사 프로필 보유 여부를 계산하고, 각 역할의 심사 상태 및 마지막 로그인 일시(last_login)를 갱신 및 결합하여 반환합니다.

    Returns:
        Response: {
            "user_id": int,
            "email": str,
            "available_roles": List[dict]
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        available_roles = []
        now = timezone.now()

        # 학생 계정이 있을 경우 role에 추가 및 last_login 업데이트
        if hasattr(user, "student_profile"):
            student = user.student_profile
            prev_last_login = student.last_login
            student.last_login = now
            student.save(update_fields=["last_login"])
            available_roles.append({
                "role": "student",
                "status": "VERIFIED",
                "last_login": prev_last_login.isoformat() if prev_last_login else None,
            })

        # 강사 계정이 있을 경우 role에 추가 및 last_login 업데이트
        if hasattr(user, "instructor_profile"):
            instructor = user.instructor_profile
            pending_info = getattr(instructor, 'pending_info', None)
            pending_status = pending_info.status if pending_info else 'NOT_SUBMITTED'
            prev_last_login = instructor.last_login
            instructor.last_login = now
            instructor.save(update_fields=["last_login"])
            available_roles.append({
                "role": "instructor",
                "status": pending_status,
                "last_login": prev_last_login.isoformat() if prev_last_login else None,
            })

        return Response({
            "user_id": user.id,
            "email": user.email,
            "available_roles": available_roles,
        }, status=status.HTTP_200_OK)


class RoleAddAPIView(APIView):
    """
    URL: /accounts/role-add/

    로그인한 유저에게 반대 역할군(학생 유저는 강사 프로필, 강사 유저는 학생 프로필)의 역할 권한을 추가로 부여하는 API View입니다.

    POST 요청 시, 쿼리 파라미터로 추가할 role을 전달받아 유효성 검사 및 프로필 생성(StudentRoleAddSerializer 또는 InstructorRoleAddSerializer 호출)을 완료합니다.
    추가 작업이 정상 수행되면 갱신된 사용자의 전체 가능 역할군 목록(available_roles)과 인증 토큰 정보를 반환합니다.

    Query Parameters:
        role (str): 추가할 역할군 ('student' | 'instructor').

    Request Body (POST):
        studentsubject (list[int], optional): 학생 프로필 추가 시의 관심 과목 번호 목록.
        university (str, optional): 강사 프로필 추가 시의 대학교명 (필수).
        department (str, optional): 강사 프로필 추가 시의 학과명.

    Returns:
        Response: {
            "token": str,
            "user_id": int,
            "email": str,
            "available_roles": List[dict]
        } (HTTP 201 Created)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = request.query_params.get('role', '').strip().lower()
        user = request.user

        if not role:
            return Response({"error": "role query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        if role not in ['student', 'instructor']:
            return Response({"error": "role query parameter must be either 'student' or 'instructor'"}, status=status.HTTP_400_BAD_REQUEST)

        if role == 'student':
            if hasattr(user, 'student_profile'):
                return Response({"error": "이미 학생 프로필이 존재합니다."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = StudentRoleAddSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()

        elif role == 'instructor':
            if hasattr(user, 'instructor_profile'):
                return Response({"error": "이미 강사 프로필이 존재합니다."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = InstructorRoleAddSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()

        # 역할이 추가된 후, 로그인 뷰와 유사하게 최신 available_roles 와 사용자 정보 반환
        available_roles = []
        if hasattr(user, 'student_profile'):
            student = user.student_profile
            available_roles.append({
                "role": "student",
                "status": "VERIFIED",
                "last_login": student.last_login.isoformat() if student.last_login else None,
            })
        if hasattr(user, 'instructor_profile'):
            instructor = user.instructor_profile
            pending_info = getattr(instructor, 'pending_info', None)
            pending_status = pending_info.status if pending_info else 'NOT_SUBMITTED'
            available_roles.append({
                "role": "instructor",
                "status": pending_status,
                "last_login": instructor.last_login.isoformat() if instructor.last_login else None,
            })

        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "token": token.key,
            "user_id": user.id,
            "email": user.email,
            "available_roles": available_roles,
        }, status=status.HTTP_201_CREATED)

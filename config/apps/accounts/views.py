from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
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
)
import logging
import random
from solapi import SolapiMessageService
from solapi.model import RequestMessage

logger = logging.getLogger(__name__)


class StudentSignupAPIView(APIView):
    """
    URL: /accounts/signup/student/

    학생용 회원가입 및 프로필 관리를 위한 API View입니다.

    Request (POST /):
        email (str): 이메일 주소.
        password (str): 비밀번호.
        user_name (str): 사용자 닉네임.
        phone (str): 전화번호.
        studentsubject (list[int]): 관심 과목 ID 리스트.

    Response (POST /):
        HTTP 201 Created:
        {
            "token": "...",
            "user_id": 1,
            "email": "user@example.com",
            "available_roles": [
                {
                    "role": "student",
                    "status": "VERIFIED",
                    "last_login": "2026-04-26T06:51:26Z"
                }
            ]
        }
    """

    def post(self, request):
        logger.debug("[BACKEND_DEBUG_AUTH] StudentSignup - START (data: %s)", request.data)
        serializer = StudentSignupSerializer(data=request.data)
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

    강사용 회원가입 및 프로필 업데이트를 처리하는 API View입니다.

    POST /accounts/signup/instructor/
    새로운 강사 계정을 생성하며, 학력/경력 인증을 위한 서류 파일(pending_file) 업로드를 필수로 요구합니다.
    회원가입 직후 강사 계정은 PENDING 상태로 지정되어 관리자 승인 후 활동이 가능합니다.

    PUT/PATCH /accounts/signup/instructor/
    강사 사용자의 프로필 정보를 수정(Partial Update)합니다.

    Args:
        request (Request): 클라이언트의 요청 객체. 포함될 주요 데이터는 다음과 같습니다.
            - email (str), password (str), user_name (str), phone (str) 등 기본 정보
            - university (str), department (str): 대학 및 학과 정보
            - pending_file (File): 인증 서류 이미지 또는 PDF (POST 요청 시 필수)

    Returns:
        Response: 처리 결과와 HTTP 상태 코드를 포함한 JSON 데이터.
            성공 시 (201 Created / 200 OK): 계정 ID, 이메일, 그리고 pending_status 반환.
            실패 시 (400 Bad Request): 유효성 검증 실패 혹은 파일 누락 사유 반환.
    """

    serializer_class = InstructorSignupSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        logger.debug("[BACKEND_DEBUG_AUTH] InstructorSignup - email: %s", request.data.get('email'))
        serializer = InstructorSignupSerializer(data=request.data)
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

    - 학생 계정은 즉시 접속 가능합니다.
    - 강사 계정은 PENDING 혹은 SUSPENDED 상태일 경우 로그인이 제한(403)됩니다.
    - 만약 학생과 강사 역할을 모두 가진 유저라면 권한 및 상태 배열(available_roles)을 반환합니다.

    Args:
        request (Request): email과 password를 포함하는 JSON 요청 데이터.

    Returns:
        Response:
            성공 (200 OK): 인증 토큰(token)과 사용자가 보유한 가능한 역할(available_roles) 반환.
            실패 (400 Bad Request): 인증 정보 불일치 혹은 파라미터 누락.
            제한 (403 Forbidden): 강사 심사가 거류(PENDING) 또는 정지(SUSPENDED)된 경우.
    """
    parser_classes = [JSONParser]  # JSON(앱) + multipart(테스트 등) 모두 허용
    permission_classes = []
    
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

    회원가입 또는 프로필 수정 과정에서 닉네임(user_name) 중복 여부를 검사하는 API View입니다.

    현재 로그인된 사용자(Token 제공 시)의 경우 자신의 기존 닉네임은 중복 체크에서 제외합니다.

    Args:
        request (Request): Query Parameters에 'user_name'이 포함되어야 합니다.

    Returns:
        Response:
            성공 (200 OK): "available": true (사용 가능) 또는 false (중복됨) 반환.
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

    회원가입 또는 프로필 수정 과정에서 이메일(email) 중복 여부를 검사하는 API View입니다.

    현재 로그인된 사용자(Token 제공 시)의 경우 자신의 기존 이메일은 중복 체크에서 제외합니다.

    Args:
        request (Request): Query Parameters에 'email'이 포함되어야 합니다.

    Returns:
        Response:
            성공 (200 OK): "available": true (사용 가능) 또는 false (중복됨) 반환.
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

    POST /accounts/logout/
    - Authorization: Token <token>
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

    POST /accounts/withdraw/
    - Authorization: Token <token>
    Body: { "reason": "더 이상 과외를 구하지 않아요", "reason_detail": "..." }
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

    입력된 휴대전화 번호로 이미 가입된 계정이 존재하는지 여부와 해당 계정의 역할을 확인합니다.

    Args:
        request (Request): Query Parameters로 'phone'을 전달받습니다.

    Returns:
        Response:
            - 미가입: "exists": false (신규 가입 가능)
            - 한쪽 역할만 가입됨: "exists": true, "missing_role": "instructor" 또는 "student" (역할 추가 가능)
            - 양쪽 모두 가입됨: "exists": true, "role_full": true (추가 가입 불가)
            - 밴(Ban)/탈퇴(Inactive) 계정 여부 포함.
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

    POST /accounts/add-role/
    - 기존 phone으로 가입된 유저에게 새로운 역할(student/instructor)을 추가합니다.
    - 토큰 불필요 (전화번호 + 비밀번호로 본인 확인)
    Body: {
        "phone": "01012345678",
        "password": "...",
        "role": "student" | "instructor",
        ...역할별 추가 필드
    }
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

    GET  /accounts/me/   — 내 프로필 조회
    PATCH /accounts/me/  — 공통 텍스트 필드 수정 (닉네임, 전화번호, 지역)

    PATCH request body (모두 optional, application/json):
    {
        "user_name": "새닉네임",
        "phone": "01012345678",
        "region": "서울|강남구"
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        logger.info(f"*** [UserProfile] Fetch profile for: {user.email} ***")
        region_parts = user.region.split(' ') if user.region else ['', '']

        return Response({
            "nickname": user.user_name,
            "last_name": user.last_name,
            "first_name": user.first_name,
            "cash": user.cash,
            "profile_image": request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
            "district": region_parts[1] if len(region_parts) > 1 else "",
            "province": region_parts[0] if len(region_parts) > 0 else "",
            "phonenumber": user.phone,
        })

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

    POST /accounts/me/phone/request/
    - 전화번호 변경을 위한 인증번호 요청
    Body: { "phone": "01012345678" }
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

    POST /accounts/me/phone/verify/
    - 인증번호 확인 후 전화번호 업데이트
    Body: { "phone": "01012345678", "code": "123456" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        phone = request.data.get('phone', '').strip()
        code = request.data.get('code', '').strip()
        
        if not all([phone, code]):
            return Response({"error": "전화번호와 인증번호가 필요합니다."}, status=400)
            
        from .models import PhoneVerification
        verification = PhoneVerification.objects.filter(
            user=request.user,
            phone=phone,
            code=code,
            is_verified=False
        ).order_by('-created_at').first()
        
        if not verification:
            return Response({"error": "인증번호가 올바르지 않거나 만료되었습니다."}, status=400)
            
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

    PATCH /accounts/me/image/  — 프로필 이미지 업로드/교체
    Content-Type: multipart/form-data
    Form field: profile_image (file)
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

    POST /accounts/signup/instructor/retry/
    - Content-Type: multipart/form-data
    - email 기반 심사 재요청 API (토큰 없이 호출 가능)
    
    필수 필드:
    - email: 유저 이메일
    - pending_file: 재심사용 서류 (파일)
    
    선택 필드 (보강 정보):
    - university, department, student_number 등
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

    GET /accounts/user/<int:pk>/
    - 특정 유저의 공개 프로필 정보를 조회합니다.
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

    GET /accounts/subjects/
    - Return the list of all available subjects
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

    POST /accounts/send-auth-sms/
    - Send authentication SMS to the given phone number

    request:
    {
        "phone_number": "01012345678"
    }

    response:
    {
        "message": "인증번호가 발송되었습니다.",
        "code": "123456"
    }
    """
    permission_classes = []

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

    POST /accounts/verify-auth-sms/
    - Verify authentication SMS with the given phone number and code

    request:
    {
        "phone_number": "01012345678",
        "code": "123456"
    }

    response:
    {
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
        verification = PhoneVerification.objects.filter(
            phone=phone_number,
            code=code,
            is_verified=False
        ).order_by('-created_at').first()
        
        if not verification:
            return Response({"error": "인증번호가 올바르지 않거나 만료되었습니다."}, status=status.HTTP_400_BAD_REQUEST)
            
        verification.is_verified = True
        verification.save(update_fields=['is_verified'])
        
        return Response({
            "message": "전화번호 인증이 완료되었습니다."
        }, status=status.HTTP_200_OK)

from django.contrib.auth import password_validation
from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from config.apps.pending.models import PendingInstructor, File

# Create your views here.
class PendingCreateAPIView(APIView):
    """
    URL: /pending/

    강사 자격 서류 제출 및 등록 상태를 조회하는 API View입니다.

    POST 요청 시, 로그인한 강사 회원이 자신의 학력/경력 인증을 위한 서류 파일(pending_file 또는 files)을 최초로 제출하고 심사 상태를 등록합니다.
    GET 요청 시, 본인의 서류 제출 유무, 인증 현황(status), 대학 및 학과 명세 정보를 반환합니다.

    Request Body (POST, Multipart):
        pending_file (File, optional): 최초 제출할 인증 서류 파일.
        files (File, optional): 다중 제출 시 서류 파일 목록.

    Returns:
        Response (POST): {
            "message": "인증 신청서와 서류가 정상적으로 접수되었습니다.",
            "status": "PENDING"
        } (HTTP 201 Created)
        Response (GET): {
            "exists": bool,
            "status": str | None,
            "university": str,
            "student_number": str,
            "field": str
        }
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        
        # 1. 강사 계정인지 검증
        if not hasattr(user, 'instructor_profile'):
            return Response({"error": "강사 프로필이 존재하지 않습니다."}, status=status.HTTP_403_FORBIDDEN)
            
        instructor = user.instructor_profile
        
        # 2. 이미 pending_info가 존재하는지 확인
        if hasattr(instructor, 'pending_info') and instructor.pending_info:
            return Response({
                "error": "이미 인증 신청 내역이 존재합니다.",
                "status": instructor.pending_info.status
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # 3. 파일 유효성 검증
        files = request.FILES.getlist('pending_file') or request.FILES.getlist('files')
        if not files:
            return Response({"error": "인증 서류(pending_file)가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
            
        # 4. PendingInstructor 및 File 생성
        pending = PendingInstructor.objects.create(
            instructor_profile=instructor,
            status=PendingInstructor.Status.PENDING
        )
        for f in files:
            File.objects.create(pending_instructor=pending, pending_file=f)
            
        return Response({
            "message": "인증 신청서와 서류가 정상적으로 접수되었습니다.",
            "status": pending.status
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        user = request.user
        
        # 1. 강사 계정인지 검증
        if not hasattr(user, 'instructor_profile'):
            return Response({"error": "강사 프로필이 존재하지 않습니다."}, status=status.HTTP_403_FORBIDDEN)
            
        instructor = user.instructor_profile
        
        # 2. pending_info 존재 여부 확인
        if not hasattr(instructor, 'pending_info') or not instructor.pending_info:
            return Response({
                "exists": False,
                "status": None,
                "university" : instructor.university,
                "student_number" : instructor.student_number,
                "field" : instructor.department,
            }, status=status.HTTP_200_OK)
            
        pending_info = instructor.pending_info
        return Response({
            "exists": True,
            "status": pending_info.status,
            "university" : instructor.university,
            "student_number" : instructor.student_number,
            "field" : instructor.department,
        }, status=status.HTTP_200_OK)



class PendingUploadView(APIView):
    """
    URL: /pending/upload/

    강사 회원이 자격 서류를 재제출(재업로드)하는 API View입니다.

    POST 요청 시 기존에 등록되었던 강사의 심사 파일을 모두 삭제하고, 새로 전달받은 서류 파일(files)로 교체하여 인증 대기 상태(PENDING)로 재심사 접수를 완료합니다.

    Request Body (Multipart):
        files (File): 새로 제출할 자격 서류 파일 목록.

    Returns:
        Response: {
            "message": "Files uploaded successfully"
        }
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        pending_instructor = user.instructor_profile.pending_info
        pending_instructor.status = PendingInstructor.Status.PENDING
        pending_instructor.save()
        
        files = request.FILES.getlist('files')
        if files:
            pending_instructor.files.all().delete()
            for file in files:
                File.objects.create(pending_instructor=pending_instructor, pending_file=file)
            return Response({"message": "Files uploaded successfully"})

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

    POST /pending/
    G
    - 로그인한 강사 회원이 인증 서류를 최초 제출할 때 호출하는 API.
    - MultipartFormData 파서 사용.
    - body field: pending_file (파일) 또는 files (다중 파일)
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
                "status": None
            }, status=status.HTTP_200_OK)
            
        pending_info = instructor.pending_info
        return Response({
            "exists": True,
            "status": pending_info.status
        }, status=status.HTTP_200_OK)



class PendingUploadView(APIView):
    """
    URL: /pending/upload/

    POST /pending/upload/
    - 강사 본인이 서류 다시 업로드(재신청) 같은 기능이 필요할 때.
    - 요구사항에 필수는 아니지만 실무에선 거의 필요해짐.
    """
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = authenticate(request, email=email, password=password)
        if not user:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        pending_instructor = user.instructor_profile.pending_info
        files = request.FILES.getlist('files')
        if files:
            pending_instructor.files.all().delete()
            for file in files:
                File.objects.create(pending_instructor=pending_instructor, pending_file=file)
            return Response({"message": "Files uploaded successfully"})

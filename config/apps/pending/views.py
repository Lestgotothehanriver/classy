from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from config.apps.pending.models import File

# Create your views here.
class PendingUploadView(APIView):
    """
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

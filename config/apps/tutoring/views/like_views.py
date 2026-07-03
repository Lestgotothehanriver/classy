from rest_framework.views import APIView
from rest_framework import status, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import logging

from config.apps.accounts.models import Student, Instructor, InstructorLike
from ..models import TutoringPost, TutoringPostLike

logger = logging.getLogger(__name__)

class InstructorLikeAPIView(APIView):
    """
    URL: /tutoring/instructors/<instructor_id>/like/

    학생이 특정 강사를 '찜(좋아요)' 하거나 취소(Toggle)하는 API View입니다.

    학생 계정(Student)을 가진 사용자만 접근 가능하며, 
    요청 시마다 좋아요 상태가 반전(Toggle)되어 현재 상태(is_liked)를 반환합니다.

    Path Parameters:
        instructor_id (int): 좋아요를 누를 대상 강사의 ID.

    Returns:
        Response: 
            {"is_liked": True/False} 및 201/200 상태 코드 반환.
            학생 계정이 아닐 시 403 에러 반환.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, instructor_id):
        try:
            student = Student.objects.get(user=request.user)
        except Student.DoesNotExist:
            return Response({"error": "학생 계정만 좋아요를 누를 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        instructor = get_object_or_404(Instructor, id=instructor_id)
        like, created = InstructorLike.objects.get_or_create(student=student, instructor=instructor)

        if not created:
            like.delete()
            return Response({"is_liked": False}, status=status.HTTP_200_OK)

        return Response({"is_liked": True}, status=status.HTTP_201_CREATED)

class TutoringPostLikeAPIView(APIView):
    """
    URL: /tutoring/posts/<post_id>/like/

    강사가 특정 '과외 구인 공고(TutoringPost)'를 '찜(좋아요)' 하거나 취소(Toggle)하는 API View입니다.

    강사 계정(Instructor)을 가진 사용자만 접근 가능하며,
    요청 시마다 좋아요 상태가 반전(Toggle)되어 현재 상태(is_liked)를 반환합니다.

    Path Parameters:
        post_id (int): 좋아요를 누를 대상 과외 공고의 ID.

    Returns:
        Response: 
            {"is_liked": True/False} 및 201/200 상태 코드 반환.
            강사 계정이 아닐 시 403 에러 반환.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, post_id):
        try:
            instructor = Instructor.objects.get(user=request.user)
        except Instructor.DoesNotExist:
            return Response({"error": "강사 계정만 좋아요를 누를 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)

        post = get_object_or_404(TutoringPost, id=post_id)
        like, created = TutoringPostLike.objects.get_or_create(instructor=instructor, post=post)

        if not created:
            like.delete()
            return Response({"is_liked": False}, status=status.HTTP_200_OK)

        return Response({"is_liked": True}, status=status.HTTP_201_CREATED)

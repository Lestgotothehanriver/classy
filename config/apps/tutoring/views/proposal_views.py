from rest_framework.views import APIView
from rest_framework import status, permissions, viewsets, mixins
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging
from config.apps.block.utils import get_blocked_user_ids

from config.apps.accounts.models import Student, Instructor
from config.apps.common.permissions import IsInstructorUser
from config.apps.chat_app.models import ChatRoom
from ..models import TutoringPost, TutoringProposal
from ..serializers import TutoringProposalSerializer
from ..services import (
    DuplicateProposalError,
    create_student_proposal_room,
    delete_student_proposal_room,
    create_instructor_proposal,
    delete_instructor_proposal,
)
from django.core.exceptions import PermissionDenied
from django.http import Http404

logger = logging.getLogger(__name__)

class StudentProposeToInstructorAPIView(APIView):
    """
    URL: /tutoring/propose-to-instructor/

    학생이 강사에게 과외 상담 및 제안을 보내고 취소하는 API View입니다.

    POST 요청 시, 학생이 특정 강사(instructor_id)에게 본인의 구인 공고(post_id)를 기반으로 과외를 신청합니다. 성공 시 대기 상태의 1:1 채팅방(ChatRoom)이 개설됩니다.
    DELETE 요청 시, 강사에게 보냈던 과외 제안을 취소하고 생성되었던 매칭 채팅방을 파기(삭제)합니다.

    Request Body (POST):
        instructor_id (int): 제안을 보낼 강사의 고유 ID (필수).
        post_id (int): 제안에 연동할 학생의 구인 공고 ID (필수).

    Request Body (DELETE) 또는 Query Parameters:
        instructor_id (int): 취소할 대상 강사 ID.
        post_id (int): 취소할 대상 구인 공고 ID.

    Returns:
        Response (POST): {
            "post_id": int,
            "room_id": int
        } (HTTP 201 Created)
        Response (DELETE): {
            "detail": "요청이 취소되었습니다."
        } (HTTP 204 No Content)
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        instructor_id = request.data.get("instructor_id")
        post_id = request.data.get("post_id")
        if not instructor_id or not post_id:
            return Response({"error": "instructor_id and post_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room, created, post = create_student_proposal_room(request.user, instructor_id, post_id)
            return Response({
                "post_id": post.id,
                "room_id": room.id,
            }, status=status.HTTP_201_CREATED)
        except DuplicateProposalError as e:
            return Response(
                {"detail": str(e), "code": "duplicate_proposal"},
                status=status.HTTP_409_CONFLICT,
            )
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Http404:
            return Response({"error": "강사나 공고를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request):
        instructor_id = request.data.get("instructor_id") or request.query_params.get("instructor_id")
        post_id = request.data.get("post_id") or request.query_params.get("post_id")

        if not instructor_id or not post_id:
            return Response({"error": "instructor_id and post_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delete_student_proposal_room(request.user, instructor_id, post_id)
            return Response({"detail": "요청이 취소되었습니다."}, status=status.HTTP_204_NO_CONTENT)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return Response({"error": "해당 제안(채팅방)을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

class InstructorProposeToStudentAPIView(APIView):
    """
    URL: /tutoring/propose-to-student/

    강사가 학생의 구인 공고를 대상으로 역제안을 하거나 취소하는 API View입니다.

    POST 요청 시, 강사 사용자가 특정 구인 공고(post_id)에 대해 한 줄 소개 메시지(message)를 작성해 역제안(TutoringProposal)을 발송하며 매칭 채팅방을 개설합니다.
    DELETE 요청 시, 보냈던 역제안 내역을 파기(삭제)하고 매칭 채팅방도 파기 처리합니다. 강사 권한이 필요합니다.

    Request Body (POST):
        post_id (int): 역제안 대상 학생 구인 공고 ID (필수).
        message (str, optional): 역제안 시 첨부할 어필 메시지 본문.

    Request Body (DELETE) 또는 Query Parameters:
        post_id (int): 취소할 대상 구인 공고 ID.

    Returns:
        Response (POST): {
            "instructor_id": int,
            "room_id": int
        } (HTTP 201 Created)
        Response (DELETE): {
            "detail": "제안이 취소되었습니다."
        } (HTTP 204 No Content)
    """
    permission_classes = [permissions.IsAuthenticated, IsInstructorUser]

    def post(self, request):
        post_id = request.data.get("post_id")
        message = request.data.get("message", "")
        if not post_id:
            return Response({"error": "post_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instructor, proposal, room, created = create_instructor_proposal(request.user, post_id, message)
            return Response({
                "instructor_id": instructor.id,
                "room_id": room.id,
            }, status=status.HTTP_201_CREATED)
        except DuplicateProposalError as e:
            return Response(
                {"detail": str(e), "code": "duplicate_proposal"},
                status=status.HTTP_409_CONFLICT,
            )
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Http404:
            return Response({"error": "공고를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request):
        post_id = request.data.get("post_id") or request.query_params.get("post_id")

        if not post_id:
            return Response({"error": "post_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delete_instructor_proposal(request.user, post_id)
            return Response({"detail": "제안이 취소되었습니다."}, status=status.HTTP_204_NO_CONTENT)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return Response({"error": "해당 제안(채팅방)을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

class TutoringProposalViewSet(mixins.ListModelMixin,
                              mixins.RetrieveModelMixin,
                              viewsets.GenericViewSet):
    """
    URL: /tutoring/proposals/
    URL: /tutoring/proposals/<pk>/

    과외 제안서(TutoringProposal)의 목록 및 상세 조회를 관리하는 API ViewSet입니다.

    GET /tutoring/proposals/ 요청 시, 조회 주체(학생 또는 강사)가 수신 및 송신한 전체 과외 제안 목록을 조회합니다. 차단된 사용자의 제안 내역은 배제됩니다.
    GET /tutoring/proposals/<pk>/ 요청 시, 특정 과외 제안서 항목의 상세 내용을 조회합니다.

    Path Parameters:
        pk (int): 대상 제안서 ID.

    Returns:
        Response (GET /tutoring/proposals/): List[TutoringProposalSerializer] 데이터
        Response (GET /tutoring/proposals/<pk>/): TutoringProposalSerializer 데이터
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringProposalSerializer

    def get_queryset(self):
        user = self.request.user
        qs = TutoringProposal.objects.filter(
            Q(instructor__user=user) | Q(tutoring_post__student__user=user)
        ).select_related("instructor", "tutoring_post", "tutoring_post__student")

        blocked_user_ids = get_blocked_user_ids(user)
        if blocked_user_ids:
            qs = qs.exclude(
                Q(instructor__user_id__in=blocked_user_ids) |
                Q(tutoring_post__student__user_id__in=blocked_user_ids)
            )
        return qs

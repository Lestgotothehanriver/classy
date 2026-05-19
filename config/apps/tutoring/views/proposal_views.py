from rest_framework.views import APIView
from rest_framework import status, permissions, viewsets, mixins
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging

from config.apps.accounts.models import Student, Instructor
from config.apps.chat_app.models import ChatRoom
from ..models import TutoringPost, TutoringProposal
from ..serializers import TutoringProposalSerializer
from ..services import (
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
    학생이 강사에게 과외 문의를 보내고 대화를 시작하는 API View입니다.

    제안 성공 시 강사와의 채팅방(ChatRoom)이 생성되며, 학생의 첫 메시지가 자동 발송됩니다.
    강사가 답장을 하면 제안이 수락된 상태로 전환됩니다.

    Request (POST):
        instructor_id (int): 문의를 받을 강사의 고유 ID.
        post_id (int): 문의의 대상이 되는 학생의 과외 공고 ID.

    Response (POST):
        HTTP 201 Created / 200 OK:
        {
            "post_id": 101
        }
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
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
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
    강사가 학생의 공고를 보고 역제안을 보내는 API View입니다.

    제안 시 제안서(TutoringProposal)와 채팅방이 생성됩니다.
    학생이 채팅방을 확인하고 답장을 보내면 제안이 성립된 것으로 간주됩니다.

    Request (POST):
        post_id (int): 제안을 보낼 학생의 과외 공고 ID.
        message (str): 학생에게 보낼 어필 메시지.

    Response (POST):
        HTTP 201 Created:
        {
            "instructor_id": 5
        }
    """
    permission_classes = [permissions.IsAuthenticated]

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
    과외 제안서(TutoringProposal)의 목록 및 상세 조회를 담당하는 API ViewSet입니다.

    읽기 전용(Read-Only) 액션만 지원하며, 조회하는 사용자(학생 혹은 강사) 본인과
    연관된 제안서만 볼 수 있도록 `get_queryset`에서 필터링됩니다.

    Actions:
        list: 본인과 연관된 모든 제안서 목록 조회.
        retrieve: 특정 제안서 상세 조회.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TutoringProposalSerializer

    def get_queryset(self):
        user = self.request.user
        return TutoringProposal.objects.filter(
            Q(instructor__user=user) | Q(tutoring_post__student__user=user)
        ).select_related("instructor", "tutoring_post", "tutoring_post__student")

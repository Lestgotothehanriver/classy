from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.db import transaction

from config.apps.accounts.models import Student, Instructor
from config.apps.chat_app.models import ChatRoom, ChatMessage
from .models import TutoringPost, TutoringProposal
from config.apps.notification.helpers import notify_tutoring_request, notify_tutoring_proposal

STUDENT_DUPLICATE_PROPOSAL_MESSAGE = "동일한 강사분에게 동일한 과외 공고가 이미 전송됐어요"
INSTRUCTOR_DUPLICATE_PROPOSAL_MESSAGE = "동일한 과외 공고에 대해서 제안서가 이미 존재해요"


class DuplicateProposalError(Exception):
    """동일한 상대와 공고 조합으로 이미 요청 또는 제안이 존재한다."""


@transaction.atomic
def create_student_proposal_room(user, instructor_id, post_id):
    """
    학생이 강사에게 과외를 제안하고 채팅방을 생성합니다.
    """
    try:
        student = Student.objects.get(user=user)
    except Student.DoesNotExist:
        raise PermissionDenied("학생 계정만 사용할 수 있습니다.")

    instructor = get_object_or_404(Instructor, id=instructor_id)
    post = get_object_or_404(TutoringPost, id=post_id, student=student)

    room, created = ChatRoom.objects.get_or_create(
        student=student,
        instructor=instructor,
        post=post,
        defaults={
            "title": f"과외 문의 - {student.user.user_name}님 & {instructor.user.user_name}님",
            "initiated_by": user,
        }
    )

    if not created:
        raise DuplicateProposalError(STUDENT_DUPLICATE_PROPOSAL_MESSAGE)

    notify_tutoring_request(room)

    # 첫 번째 안내 메시지 전송 (학생)
    initial_text = f"{student.user.user_name} 님이 선생님에게 과외 상담 요청을 보냈습니다."
    ChatMessage.objects.create(
        room=room,
        sender=user,
        text=initial_text
    )

    return room, created, post


def delete_student_proposal_room(user, instructor_id, post_id):
    """
    학생이 보낸 과외 제안(채팅방)을 취소/삭제합니다.
    """
    try:
        student = Student.objects.get(user=user)
    except Student.DoesNotExist:
        raise PermissionDenied("학생 계정만 사용할 수 있습니다.")

    instructor = get_object_or_404(Instructor, id=instructor_id)
    post = get_object_or_404(TutoringPost, id=post_id, student=student)

    room = get_object_or_404(ChatRoom, student=student, instructor=instructor, post=post, initiated_by=user)
    
    if getattr(room, 'is_accepted', False):
        raise ValueError("이미 수락된 요청은 삭제할 수 없습니다.")
        
    room.delete()


@transaction.atomic
def create_instructor_proposal(user, post_id, message):
    """
    강사가 학생의 공고에 과외를 제안하고 채팅방을 생성합니다.
    """
    try:
        instructor = Instructor.objects.get(user=user)
    except Instructor.DoesNotExist:
        raise PermissionDenied("선생님 계정만 사용할 수 있습니다.")

    post = get_object_or_404(TutoringPost, id=post_id)

    if TutoringProposal.objects.filter(
        tutoring_post=post,
        instructor=instructor,
    ).exists():
        raise DuplicateProposalError(INSTRUCTOR_DUPLICATE_PROPOSAL_MESSAGE)

    room, created = ChatRoom.objects.get_or_create(
        student=post.student,
        instructor=instructor,
        post=post,
        defaults={
            "title": f"제안서 문의 - {post.student.user.username}님 & {instructor.user.username}님",
            "initiated_by": user,
        }
    )

    if not created:
        raise DuplicateProposalError(INSTRUCTOR_DUPLICATE_PROPOSAL_MESSAGE)

    proposal = TutoringProposal.objects.create(
        tutoring_post=post,
        instructor=instructor,
        message=message
    )

    notify_tutoring_proposal(room)

    # 첫 번째 안내 메시지 전송 (선생님 제안서 원문)
    ChatMessage.objects.create(
        room=room,
        sender=user,
        text=message
    )

    return instructor, proposal, room, created


def delete_instructor_proposal(user, post_id):
    """
    강사가 보낸 과외 제안 및 채팅방을 취소/삭제합니다.
    """
    try:
        instructor = Instructor.objects.get(user=user)
    except Instructor.DoesNotExist:
        raise PermissionDenied("선생님 계정만 사용할 수 있습니다.")

    post = get_object_or_404(TutoringPost, id=post_id)

    try:
        proposal = TutoringProposal.objects.get(tutoring_post=post, instructor=instructor)
        proposal.delete()
    except TutoringProposal.DoesNotExist:
        pass

    room = get_object_or_404(ChatRoom, student=post.student, instructor=instructor, post=post, initiated_by=user)
    
    if getattr(room, 'is_accepted', False):
        raise ValueError("이미 수락된 요청은 삭제할 수 없습니다.")
        
    room.delete()

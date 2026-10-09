"""Erase account identity and UGC without cascading through financial ledgers.

Unusable, anonymous relational stubs preserve transaction/contract integrity.
Payment, settlement and dispute evidence remains under the published retention
policy; it is not an active account and must never be restored as one.
"""
import logging
import uuid

from django.contrib.auth import get_user_model
from django.apps import apps
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import DeletedAccountFile, PhoneVerification, UserConsent

logger = logging.getLogger(__name__)


def purge_deleted_files(limit=100):
    """Idempotent, retryable storage deletion, always after the DB commit."""
    removed = 0
    for job in DeletedAccountFile.objects.order_by('pk')[:limit]:
        try:
            from django.db.models import FileField
            # A shared asset still owned by another record is not ours to erase.
            referenced = any(
                model.objects.filter(**{field.name: job.name}).exists()
                for model in apps.get_models()
                for field in model._meta.fields
                if isinstance(field, FileField)
            )
            if not referenced:
                default_storage.delete(job.name)
        except Exception:
            DeletedAccountFile.objects.filter(pk=job.pk).update(attempts=F('attempts') + 1)
            logger.exception('Account file removal failed; queued job=%s', job.pk)
        else:
            job.delete()
            removed += 1
    return removed


def _queue_files(queryset, *fields):
    for row in queryset.values_list(*fields):
        for name in row:
            if name:
                DeletedAccountFile.objects.get_or_create(name=name)


def _close_connections(user_id, room_ids):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    layer = get_channel_layer()
    if layer is None:
        return
    for group in [f'notification_user_{user_id}', *[f'chat_{pk}' for pk in room_ids]]:
        async_to_sync(layer.group_send)(group, {'type': 'account.deleted', 'user_id': user_id})


@transaction.atomic
def delete_account(user_id):
    from config.apps.accounts.models import Instructor, Student, InstructorLike, StudentLike
    from config.apps.block.models import Block
    from config.apps.cash.models import Account, InstructorMonthlyRank
    from config.apps.chat_app.models import ChatMessage, ChatRoom, Image, UserDeviceToken
    from config.apps.lecture.models import Lecture, Comment, SearchHistory
    from config.apps.notification.models import DeviceToken, Notification
    from config.apps.pending.models import PendingInstructor, File
    from config.apps.tutoring.models import (
        InstructorInfo, InstructorReview, StudentReview, TutoringPost, TutoringProposal,
        TutoringPostLike,
    )
    from config.apps.support.services import anonymize_user_tickets

    User = get_user_model()
    user = User.objects.select_for_update().get(pk=user_id)
    if user.deleted_at:
        return
    now = timezone.now()
    # 문의 처리 이력은 보관하되 탈퇴 후에는 본인 식별·첨부 열람이 불가능해야 합니다.
    anonymize_user_tickets(user)
    student = Student.objects.filter(user=user).first()
    instructor = Instructor.objects.filter(user=user).first()
    rooms = ChatRoom.objects.filter(Q(student__user=user) | Q(instructor__user=user))
    room_ids = list(rooms.values_list('pk', flat=True))

    # Remove copies in event notifications as well as the user's own inbox.
    Notification.objects.filter(user=user).delete()
    for room_id in room_ids:
        Notification.objects.filter(Q(data__room_id=str(room_id)) | Q(data__room_id=room_id)).delete()
    DeviceToken.objects.filter(user=user).delete()
    UserDeviceToken.objects.filter(user=user).delete()
    Token.objects.filter(user=user).delete()
    phone_filter = Q(user=user)
    if user.phone:
        phone_filter |= Q(phone=user.phone)
    PhoneVerification.objects.filter(phone_filter).delete()
    UserConsent.objects.filter(user=user).delete()
    Block.objects.filter(Q(user=user) | Q(blocked_user=user)).delete()

    # Uploaded chat images and authored text are erased. Other participants'
    # messages and signed contracts are not cascaded away.
    images = Image.objects.filter(message__sender=user)
    _queue_files(images, 'image')
    images.delete()
    ChatMessage.objects.filter(sender=user).delete()
    ChatMessage.read_by.through.objects.filter(user_id=user.pk).delete()
    ChatRoom.liked_by.through.objects.filter(user_id=user.pk).delete()
    ChatRoom.muted_by.through.objects.filter(user_id=user.pk).delete()
    rooms.update(title='')
    # A blank comment tombstone preserves other people's reply threads.
    Comment.objects.filter(author=user).update(content='', is_blocked=True, blocked_at=now, referenced_person=None)
    Comment.objects.filter(referenced_person=user).update(referenced_person=None)

    if student:
        student.subjects.clear()
        SearchHistory.objects.filter(student=student).delete()
        InstructorLike.objects.filter(student=student).delete()
        StudentLike.objects.filter(student=student).delete()
        InstructorReview.objects.filter(student=student).delete()
        posts = TutoringPost.objects.filter(student=student)
        # Posts/rooms may be protected by a historical contract. Erase their
        # content in place instead of deleting contracts or blocking withdrawal.
        for post in posts:
            post.subjects.clear()
            post.regions.clear()
        posts.update(title='', sex='', age=None, grade='', field='', method='', cost=None,
                     schedule='', situation='', etc='', is_active=False)
        TutoringProposal.objects.filter(tutoring_post__student=student).delete()
        TutoringPostLike.objects.filter(tutoring_post__student=student).delete()
        Lecture.likes.through.objects.filter(student_id=student.pk).delete()
    if instructor:
        pending = PendingInstructor.objects.filter(instructor_profile=instructor)
        _queue_files(File.objects.filter(pending_instructor__in=pending), 'pending_file')
        pending.delete()
        InstructorInfo.objects.filter(instructor=instructor).delete()
        InstructorLike.objects.filter(instructor=instructor).delete()
        StudentLike.objects.filter(instructor=instructor).delete()
        StudentReview.objects.filter(instructor=instructor).delete()
        TutoringProposal.objects.filter(instructor=instructor).delete()
        TutoringPostLike.objects.filter(instructor=instructor).delete()
        InstructorMonthlyRank.objects.filter(instructor=instructor).delete()
        instructor.subjects.clear()
        Instructor.objects.filter(pk=instructor.pk).update(
            university='', department='', instruction='', student_number='', is_tutoring=False)
        # Keep bank details only when needed by an existing settlement record.
        if not instructor.settlements.exists():
            Account.objects.filter(instructor=instructor).delete()
        lectures = Lecture.objects.filter(instructor=instructor)
        _queue_files(lectures, 'video', 'thumbnail')
        for lecture in lectures:
            lecture.subjects.clear()
            lecture.likes.clear()
        lectures.update(title='삭제된 강의', video='', thumbnail='', video_duration=0,
                        is_active=False, is_delete=True, deleted_at=now, suspended_at=now)

    if user.profile_image:
        DeletedAccountFile.objects.get_or_create(name=user.profile_image.name)
    anonymous_id = uuid.uuid4().hex
    user.username = 'deleted_' + anonymous_id
    user.user_name = '탈퇴회원_' + anonymous_id[:12]
    user.email = ''
    user.phone = None
    user.first_name = user.last_name = user.sex = user.region = user.field = ''
    user.birth_date = None
    user.profile_image = ''
    user.withdraw_reason = user.withdraw_reason_detail = ''
    user.marketing_opt_in = False
    user.is_active = False
    user.deleted_at = now
    user.last_login = None
    user.set_unusable_password()
    user.save()
    # Keep cash/ledger identifiers intact for store refunds, reconciliation and
    # statutory retention, but there is no remaining credential to this wallet.
    transaction.on_commit(purge_deleted_files, robust=True)
    transaction.on_commit(lambda: _close_connections(user_id, room_ids), robust=True)

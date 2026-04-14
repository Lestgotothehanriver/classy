from django.db.models.signals import post_save
from django.dispatch import receiver

from config.apps.tutoring.models import TutoringProposal
from config.apps.chat_app.notifications import push_to_users
from .models import Notification


def _save_and_push(user_ids, type_, title, body, data, username):
    """Notification DB 저장 + FCM 푸시 발송"""
    Notification.objects.bulk_create([
        Notification(user_id=uid, type=type_, title=title, body=body, data=data)
        for uid in user_ids
    ])
    push_to_users(user_ids, title=title, body=body, username=username, data=data)


@receiver(post_save, sender=TutoringProposal)
def notify_tutoring_proposal(sender, instance: TutoringProposal, created: bool, **kwargs):
    """강사가 과외 제안을 보낼 때 학생에게 알림"""
    if not created:
        return

    student_user = instance.tutoring_post.student.user
    instructor_name = instance.instructor.user.username
    title = "새 과외 제안이 도착했습니다"
    body = instance.message or f"{instructor_name}님이 과외 제안을 보냈습니다."
    data = {
        "type": "tutoring_proposal",
        "proposal_id": str(instance.id),
        "post_id": str(instance.tutoring_post.id),
        "instructor_id": str(instance.instructor.id),
    }
    _save_and_push([student_user.id], "tutoring_proposal", title, body, data, instructor_name)
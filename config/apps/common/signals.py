import logging
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from config.apps.accounts.models import User
from config.apps.lecture.models import Lecture
from config.apps.tutoring.models import TutoringResource, TutoringResourceFile

logger = logging.getLogger(__name__)

def delete_file_field(instance, field_name):
    """
    파일 필드에 연결된 물리적 파일을 스토리지에서 삭제합니다.
    """
    try:
        file_field = getattr(instance, field_name)
        if file_field and file_field.name:
            file_field.delete(save=False)
            logger.debug(f"[FILE CLEANUP] Deleted {field_name} for {instance.__class__.__name__} ({instance.pk})")
    except Exception as e:
        logger.error(f"[FILE CLEANUP ERROR] Failed to delete {field_name} for {instance.__class__.__name__} ({instance.pk}): {e}")


@receiver(post_delete, sender=User)
def cleanup_user_profile_image(sender, instance, **kwargs):
    delete_file_field(instance, 'profile_image')

@receiver(pre_save, sender=User)
def cleanup_old_user_profile_image(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = User.objects.get(pk=instance.pk)
        if old_instance.profile_image and old_instance.profile_image != instance.profile_image:
            delete_file_field(old_instance, 'profile_image')
    except User.DoesNotExist:
        pass


@receiver(post_delete, sender=Lecture)
def cleanup_lecture_files(sender, instance, **kwargs):
    delete_file_field(instance, 'thumbnail')
    delete_file_field(instance, 'video')

@receiver(pre_save, sender=Lecture)
def cleanup_old_lecture_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = Lecture.objects.get(pk=instance.pk)
        if old_instance.thumbnail and old_instance.thumbnail != instance.thumbnail:
            delete_file_field(old_instance, 'thumbnail')
        if old_instance.video and old_instance.video != instance.video:
            delete_file_field(old_instance, 'video')
    except Lecture.DoesNotExist:
        pass


@receiver(post_delete, sender=TutoringResourceFile)
def cleanup_tutoring_resource_file(sender, instance, **kwargs):
    delete_file_field(instance, 'file')

@receiver(post_delete, sender=TutoringResource)
def cleanup_tutoring_resource_fee_file(sender, instance, **kwargs):
    delete_file_field(instance, 'fee_confirmation_file')

@receiver(pre_save, sender=TutoringResource)
def cleanup_old_tutoring_resource_fee_file(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = TutoringResource.objects.get(pk=instance.pk)
        if old_instance.fee_confirmation_file and old_instance.fee_confirmation_file != instance.fee_confirmation_file:
            delete_file_field(old_instance, 'fee_confirmation_file')
    except TutoringResource.DoesNotExist:
        pass

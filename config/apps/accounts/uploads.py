import logging
import re
from pathlib import Path
from uuid import uuid4

from django.db import transaction

logger = logging.getLogger(__name__)


def profile_image_upload_to(instance, filename):
    """Return an immutable, user-scoped storage path for a profile image."""
    if instance.pk is None:
        raise ValueError("A saved user is required before uploading a profile image.")

    suffix = Path(filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = ""

    return f"profile_images/{instance.pk}/{uuid4().hex}{suffix}"


def _delete_replaced_profile_image(*, user_id, old_name, storage):
    """Delete [old_name] only when it is no longer the user's current image."""
    from .models import User

    try:
        current_name = (
            User.objects.filter(pk=user_id)
            .values_list("profile_image", flat=True)
            .first()
        )
        if current_name != old_name:
            storage.delete(old_name)
    except Exception:
        logger.exception(
            "Failed to delete replaced profile image %s for user %s",
            old_name,
            user_id,
        )


def replace_profile_image(*, user_id, uploaded_file):
    """Atomically replace one user's profile image and return the locked user."""
    from .models import User

    image_field = User._meta.get_field("profile_image")
    new_storage = image_field.storage
    new_name = None

    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user_id)
            old_file = user.profile_image
            old_name = old_file.name if old_file else None
            old_storage = old_file.storage

            generated_name = image_field.generate_filename(
                user,
                uploaded_file.name,
            )
            new_name = new_storage.save(generated_name, uploaded_file)

            user.profile_image = new_name
            user.save(update_fields=["profile_image"])

            if old_name and old_name != new_name:
                transaction.on_commit(
                    lambda: _delete_replaced_profile_image(
                        user_id=user.pk,
                        old_name=old_name,
                        storage=old_storage,
                    )
                )

        return user
    except Exception:
        if new_name:
            try:
                new_storage.delete(new_name)
            except Exception:
                logger.exception(
                    "Failed to delete orphaned profile image %s for user %s",
                    new_name,
                    user_id,
                )
        raise

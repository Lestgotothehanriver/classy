from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from config.apps.accounts.uploads import (
    _delete_replaced_profile_image,
    replace_profile_image,
)
from config.apps.common.media import serve_media_with_range

User = get_user_model()


class TemporaryMediaMixin:
    """Run each test against an isolated filesystem media root."""

    def setUp(self):
        super().setUp()
        self.media_directory = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()
        super().tearDown()


class ProfileImageReplacementTests(TemporaryMediaMixin, APITestCase):
    """Verify immutable profile paths and transactional replacement cleanup."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="profile@example.com",
            email="profile@example.com",
            user_name="profile-user",
            password="pass1234",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("accounts:user-profile-image")

    def _upload(self, content):
        return self.client.patch(
            self.url,
            {
                "profile_image": SimpleUploadedFile(
                    "SAME-NAME.JPG",
                    content,
                    content_type="image/jpeg",
                )
            },
            format="multipart",
        )

    def test_same_original_filename_gets_new_url_and_deletes_old_file(self):
        with self.captureOnCommitCallbacks(execute=True):
            first_response = self._upload(b"first-image")

        self.user.refresh_from_db()
        first_name = self.user.profile_image.name
        first_path = Path(self.user.profile_image.path)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(
            first_response.data,
            {"profile_image": first_response.wsgi_request.build_absolute_uri(
                self.user.profile_image.url
            )},
        )
        self.assertRegex(
            first_name,
            rf"^profile_images/{self.user.pk}/[0-9a-f]{{32}}\.jpg$",
        )
        self.assertTrue(first_path.exists())

        with self.captureOnCommitCallbacks(execute=True):
            second_response = self._upload(b"second-image")

        self.user.refresh_from_db()
        second_name = self.user.profile_image.name

        self.assertEqual(second_response.status_code, 200)
        self.assertNotEqual(first_name, second_name)
        self.assertNotEqual(
            first_response.data["profile_image"],
            second_response.data["profile_image"],
        )
        self.assertFalse(first_path.exists())
        self.assertTrue(Path(self.user.profile_image.path).exists())

    def test_database_failure_keeps_old_file_and_removes_new_orphan(self):
        self.user.profile_image.save(
            "old.png",
            ContentFile(b"old-image"),
            save=True,
        )
        old_name = self.user.profile_image.name
        old_path = Path(self.user.profile_image.path)

        with patch.object(User, "save", side_effect=IntegrityError("forced failure")):
            with self.assertRaises(IntegrityError):
                replace_profile_image(
                    user_id=self.user.pk,
                    uploaded_file=SimpleUploadedFile(
                        "new.png",
                        b"new-image",
                        content_type="image/png",
                    ),
                )

        self.user.refresh_from_db()
        stored_files = [path for path in Path(self.media_directory.name).rglob("*") if path.is_file()]

        self.assertEqual(self.user.profile_image.name, old_name)
        self.assertTrue(old_path.exists())
        self.assertEqual(stored_files, [old_path])

    def test_cleanup_callback_never_deletes_current_database_path(self):
        self.user.profile_image.save(
            "current.webp",
            ContentFile(b"current-image"),
            save=True,
        )
        current_path = Path(self.user.profile_image.path)

        _delete_replaced_profile_image(
            user_id=self.user.pk,
            old_name=self.user.profile_image.name,
            storage=self.user.profile_image.storage,
        )

        self.assertTrue(current_path.exists())

    def test_deleting_user_removes_current_profile_file(self):
        self.user.profile_image.save(
            "current.png",
            ContentFile(b"current-image"),
            save=True,
        )
        current_path = Path(self.user.profile_image.path)

        self.user.delete()

        self.assertFalse(current_path.exists())

    def test_legacy_database_path_remains_readable(self):
        legacy_name = "profile_images/legacy-avatar.jpg"
        legacy_path = Path(self.media_directory.name, legacy_name)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(b"legacy-image")
        User.objects.filter(pk=self.user.pk).update(profile_image=legacy_name)

        self.user.refresh_from_db()

        self.assertEqual(self.user.profile_image.name, legacy_name)
        self.assertTrue(Path(self.user.profile_image.path).exists())


class ProfileImageCacheHeaderTests(TemporaryMediaMixin, SimpleTestCase):
    """Ensure immutable caching is scoped to profile images only."""

    def setUp(self):
        super().setUp()
        self.request_factory = RequestFactory()

    def _write_media(self, relative_path):
        media_path = Path(self.media_directory.name, relative_path)
        media_path.parent.mkdir(parents=True, exist_ok=True)
        media_path.write_bytes(b"media")

    def test_profile_image_response_is_immutable(self):
        relative_path = "profile_images/123/versioned.jpg"
        self._write_media(relative_path)

        response = serve_media_with_range(
            self.request_factory.get(f"/media/{relative_path}"),
            relative_path,
        )
        try:
            self.assertEqual(
                response["Cache-Control"],
                "public, max-age=31536000, immutable",
            )
        finally:
            response.close()

    def test_other_media_response_does_not_get_profile_cache_policy(self):
        relative_path = "lectures/thumbnail.jpg"
        self._write_media(relative_path)

        response = serve_media_with_range(
            self.request_factory.get(f"/media/{relative_path}"),
            relative_path,
        )
        try:
            self.assertNotIn("Cache-Control", response)
        finally:
            response.close()

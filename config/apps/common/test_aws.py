from unittest.mock import patch
import tempfile
from django.core.files import File

from django.test import SimpleTestCase, override_settings

from config.apps.lecture.utils import resolve_video_path


@override_settings(DEBUG=False, AWS_STORAGE_BUCKET_NAME='test-private-bucket')
class S3MediaTests(SimpleTestCase):
    def test_legacy_media_url_redirects_to_signed_s3_url(self):
        with patch('config.apps.common.media.default_storage') as storage:
            storage.exists.return_value = True
            storage.url.return_value = 'https://example.s3.amazonaws.com/video.mp4?signature=test'
            response = self.client.get('/media/lectures/videos/video.mp4')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://example.s3.amazonaws.com/video.mp4?signature=test')
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_protected_files_never_receive_a_signed_url(self):
        with patch('config.apps.common.media.default_storage') as storage:
            response = self.client.get('/media/files/verification.pdf')
        self.assertEqual(response.status_code, 404)
        storage.url.assert_not_called()

    def test_dot_segments_cannot_bypass_private_document_restriction(self):
        with patch('config.apps.common.media.default_storage') as storage:
            response = self.client.get('/media/profile_images/../files/verification.pdf')
        self.assertEqual(response.status_code, 404)
        storage.url.assert_not_called()

    def test_missing_file_is_404(self):
        with patch('config.apps.common.media.default_storage') as storage:
            storage.exists.return_value = False
            response = self.client.get('/media/lectures/videos/missing.mp4')
        self.assertEqual(response.status_code, 404)

    def test_s3_file_without_local_path_does_not_raise(self):
        class RemoteFile:
            @property
            def path(self):
                raise NotImplementedError('No local path')
        self.assertIsNone(resolve_video_path(RemoteFile()))

    def test_converted_video_uses_underlying_temporary_file_path(self):
        with tempfile.NamedTemporaryFile(suffix='.mp4') as temporary:
            converted = File(temporary, name='display-name.mp4')
            self.assertEqual(resolve_video_path(converted), temporary.name)


class HealthTests(SimpleTestCase):
    def test_failed_database_is_service_unavailable(self):
        with patch('config.apps.common.health.connection') as connection:
            connection.cursor.side_effect = RuntimeError('private internal details')
            response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})

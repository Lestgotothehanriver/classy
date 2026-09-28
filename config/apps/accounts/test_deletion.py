from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .deletion import delete_account, purge_deleted_files
from .models import Student, Instructor, DeletedAccountFile, PhoneVerification
from config.apps.cash.models import PurchaseHistory, LectureRentalHistory
from config.apps.lecture.models import Lecture, Comment
from config.apps.notification.models import DeviceToken


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
                   CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class AccountDeletionTests(APITestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(
            username='delete@example.com', email='delete@example.com', user_name='delete-me',
            password='StrongPass123!', phone='01011112222', first_name='Private',
            last_name='Person', birth_date='2000-01-01', sex='여성', region='서울',
            marketing_opt_in=True)
        Student.objects.create(user=self.user)
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def test_endpoint_erases_identity_tokens_and_photo_then_rejects_old_credentials(self):
        self.user.profile_image.save('private.png', ContentFile(b'private'), save=True)
        photo = self.user.profile_image.name
        DeviceToken.objects.create(user=self.user, token='device-private')
        PhoneVerification.objects.create(phone=self.user.phone, code='123456')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/accounts/withdraw/', {'reason_detail': 'private text'})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deleted_at)
        self.assertEqual(self.user.email, '')
        self.assertIsNone(self.user.phone)
        self.assertIsNone(self.user.birth_date)
        self.assertEqual(self.user.first_name + self.user.last_name + self.user.region, '')
        self.assertEqual(self.user.withdraw_reason_detail, '')
        self.assertFalse(self.user.marketing_opt_in)
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertFalse(DeviceToken.objects.filter(user=self.user).exists())
        self.assertFalse(PhoneVerification.objects.exists())
        self.assertFalse(default_storage.exists(photo))
        self.assertEqual(self.client.get('/accounts/me/').status_code, 401)
        self.client.credentials()
        login = self.client.post('/accounts/login/', {'email': 'delete@example.com', 'password': 'StrongPass123!'}, format='json')
        self.assertEqual(login.status_code, 400)

    def test_instructor_content_erased_without_destroying_other_user_or_financial_history(self):
        instructor = Instructor.objects.create(user=self.user, university='Private University', instruction='Private bio')
        other = get_user_model().objects.create_user(username='other', email='other@example.com', user_name='other')
        lecture = Lecture.objects.create(instructor=instructor, title='Private title', price=500,
                                        video='lectures/private.mp4', thumbnail='lectures/private.png')
        purchase = PurchaseHistory.objects.create(user=self.user, platform='apple', transaction_id='test-retain', purchased_cash=500, paid_amount=1000, fee_deducted_amount=700, remaining_cash=500)
        rental = LectureRentalHistory.objects.create(student=other, lecture=lecture, purchased_cash=500, remaining_cash=0)
        parent = Comment.objects.create(lecture=lecture, author=self.user, content='Private comment')
        reply = Comment.objects.create(lecture=lecture, author=other, parent=parent, content='Other person reply')
        delete_account(self.user.pk)
        instructor.refresh_from_db(); lecture.refresh_from_db(); parent.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(instructor.university + instructor.instruction, '')
        self.assertEqual(lecture.video.name, '')
        self.assertTrue(lecture.is_delete)
        self.assertFalse(lecture.is_active)
        self.assertEqual(parent.content, '')
        self.assertTrue(Comment.objects.filter(pk=reply.pk, content='Other person reply').exists())
        self.assertTrue(PurchaseHistory.objects.filter(pk=purchase.pk).exists())
        self.assertTrue(LectureRentalHistory.objects.filter(pk=rental.pk).exists())
        self.assertEqual(other.email, 'other@example.com')
        self.assertTrue(other.is_active)
        self.assertEqual(DeletedAccountFile.objects.count(), 2)

    def test_storage_error_is_durable_and_retryable(self):
        path = default_storage.save('retry.png', ContentFile(b'data'))
        job = DeletedAccountFile.objects.create(name=path)
        with patch('config.apps.accounts.deletion.default_storage.delete', side_effect=OSError('offline')):
            self.assertEqual(purge_deleted_files(), 0)
        job.refresh_from_db(); self.assertEqual(job.attempts, 1)
        self.assertEqual(purge_deleted_files(), 1)
        self.assertFalse(default_storage.exists(path))

    def test_rollback_does_not_delete_storage_or_credentials(self):
        self.user.profile_image.save('rollback.png', ContentFile(b'data'), save=True)
        path = self.user.profile_image.name
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    delete_account(self.user.pk)
                    raise RuntimeError('rollback')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.deleted_at)
        self.assertTrue(Token.objects.filter(user=self.user).exists())
        self.assertTrue(default_storage.exists(path))
        self.assertFalse(DeletedAccountFile.objects.exists())

    def test_idempotent_and_does_not_remove_a_shared_file(self):
        self.user.profile_image.save('shared.png', ContentFile(b'data'), save=True)
        path = self.user.profile_image.name
        other = get_user_model().objects.create_user(username='other', user_name='other', profile_image=path)
        with self.captureOnCommitCallbacks(execute=True):
            delete_account(self.user.pk)
        self.assertTrue(default_storage.exists(path))
        self.user.refresh_from_db(); name = self.user.username
        delete_account(self.user.pk)
        self.user.refresh_from_db(); self.assertEqual(self.user.username, name)

    def test_unauthenticated_deletion_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.post('/accounts/withdraw/').status_code, 401)
        self.user.refresh_from_db(); self.assertTrue(self.user.is_active)

    def test_protected_contract_does_not_prevent_erasure_of_chat_and_files(self):
        from config.apps.chat_app.models import ChatRoom, ChatMessage, Image
        from config.apps.tutoring.models import TutoringPost, TutoringRegistration
        instructor = Instructor.objects.create(user=self.user, university='Private University')
        other = get_user_model().objects.create_user(username='other', user_name='other')
        student = Student.objects.create(user=other)
        post = TutoringPost.objects.create(student=student, title='Other post')
        room = ChatRoom.objects.create(student=student, instructor=instructor, post=post)
        contract = TutoringRegistration.objects.create(student=other, instructor=self.user, chat_room=room,
                                                       subject='수학', start_date='2026-09-01')
        authored, theirs = ChatMessage.objects.bulk_create([
            ChatMessage(room=room, sender=self.user, text='Private message'),
            ChatMessage(room=room, sender=other, text='Other message'),
        ])
        image = Image.objects.create(message=authored)
        image.image.save('chat-private.png', ContentFile(b'private'), save=True)
        path = image.image.name
        with self.captureOnCommitCallbacks(execute=True):
            delete_account(self.user.pk)
        self.assertTrue(TutoringRegistration.objects.filter(pk=contract.pk).exists())
        self.assertFalse(ChatMessage.objects.filter(pk=authored.pk).exists())
        self.assertTrue(ChatMessage.objects.filter(pk=theirs.pk).exists())
        self.assertFalse(default_storage.exists(path))

    def test_socket_revocation_only_closes_deleted_users_connections(self):
        from asgiref.sync import async_to_sync
        from unittest.mock import AsyncMock
        from config.apps.chat_app.consumers import ChatConsumer
        from config.apps.notification.consumers import NotificationConsumer
        for consumer_class in (ChatConsumer, NotificationConsumer):
            consumer = consumer_class()
            consumer.user = self.user
            consumer.close = AsyncMock()
            async_to_sync(consumer.account_deleted)({'user_id': self.user.pk + 1})
            consumer.close.assert_not_called()
            async_to_sync(consumer.account_deleted)({'user_id': self.user.pk})
            consumer.close.assert_awaited_once_with(code=4001)

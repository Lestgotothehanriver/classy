"""마케팅 FCM 예약 발송과 동의 API 회귀 테스트입니다."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from config.apps.accounts.models import UserConsent
from config.apps.notification.marketing import dispatch_marketing_campaign, dispatch_due_marketing_campaigns
from config.apps.notification.models import (
    DeviceToken,
    MarketingPushCampaign,
    MarketingPushMacro,
    Notification,
)


User = get_user_model()


def make_user(email: str, *, marketing_opt_in: bool = True, superuser: bool = False):
    """[email]을 사용하는 테스트 계정을 생성합니다."""
    user = User.objects.create_user(
        username=email,
        email=email,
        user_name=email,
        password='Passw0rd!123',
        marketing_opt_in=marketing_opt_in,
    )
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=['is_superuser', 'is_staff'])
    return user


class MarketingCampaignDispatchTests(APITestCase):
    """마케팅 발송 대상 필터와 알림센터 저장을 검증합니다."""

    def setUp(self):
        """학생·선생님·겸업·미동의·비활성 단말을 준비합니다."""
        self.student = make_user('student@example.com')
        self.instructor = make_user('instructor@example.com')
        self.dual_role = make_user('dual@example.com')
        self.opted_out = make_user('opted-out@example.com', marketing_opt_in=False)
        self.inactive = make_user('inactive@example.com')
        DeviceToken.objects.create(user=self.student, token='student-token', active_role='student')
        DeviceToken.objects.create(user=self.instructor, token='instructor-token', active_role='instructor')
        DeviceToken.objects.create(user=self.dual_role, token='dual-student-token', active_role='student')
        DeviceToken.objects.create(user=self.dual_role, token='dual-instructor-token', active_role='instructor')
        DeviceToken.objects.create(user=self.opted_out, token='opted-out-token', active_role='student')
        DeviceToken.objects.create(user=self.inactive, token='inactive-token', active_role='student', is_active=False)

    def campaign(self, **overrides):
        """현재 시각에 실행 가능한 기본 캠페인을 생성합니다."""
        values = {
            'target_role': MarketingPushCampaign.TargetRole.STUDENT,
            'title': '학생 이벤트',
            'body': '학생 대상 혜택입니다.',
            'scheduled_at': timezone.now(),
            'push_only': False,
        }
        values.update(overrides)
        return MarketingPushCampaign.objects.create(**values)

    @patch('config.apps.notification.marketing._send_fcm_batches')
    def test_student_campaign_filters_by_opt_in_active_token_and_role(self, send_fcm):
        """학생 활성 역할 단말만 FCM과 알림센터 대상이 됩니다."""
        campaign = self.campaign()
        send_fcm.return_value = (2, 0)

        dispatched = dispatch_marketing_campaign(campaign.pk)

        self.assertIsNotNone(dispatched)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, MarketingPushCampaign.Status.COMPLETED)
        self.assertEqual(campaign.recipient_count, 2)
        self.assertEqual(campaign.token_count, 2)
        self.assertEqual(campaign.success_count, 2)
        self.assertEqual(
            set(Notification.objects.filter(type='marketing').values_list('user_id', 'role')),
            {(self.student.id, 'student'), (self.dual_role.id, 'student')},
        )
        send_fcm.assert_called_once()

    @patch('config.apps.notification.marketing._send_fcm_batches')
    def test_all_campaign_keeps_dual_role_notification_center_entries_separate(self, send_fcm):
        """전체 발송은 겸업 사용자의 각 활성 역할 알림센터 항목을 분리합니다."""
        campaign = self.campaign(target_role=MarketingPushCampaign.TargetRole.ALL)
        send_fcm.return_value = (4, 0)

        dispatch_marketing_campaign(campaign.pk)

        self.assertEqual(Notification.objects.filter(type='marketing').count(), 4)
        self.assertEqual(
            set(Notification.objects.filter(type='marketing').values_list('user_id', 'role')),
            {
                (self.student.id, 'student'),
                (self.instructor.id, 'instructor'),
                (self.dual_role.id, 'student'),
                (self.dual_role.id, 'instructor'),
            },
        )

    @patch('config.apps.notification.marketing._send_fcm_batches')
    def test_push_only_campaign_does_not_write_notification_center(self, send_fcm):
        """기본 푸시 전용 옵션은 알림센터 레코드를 만들지 않습니다."""
        campaign = self.campaign(push_only=True)
        send_fcm.return_value = (2, 0)

        dispatch_marketing_campaign(campaign.pk)

        self.assertFalse(Notification.objects.filter(type='marketing').exists())

    @patch('config.apps.notification.marketing._send_fcm_batches')
    def test_due_dispatch_is_idempotent_and_skips_future_campaign(self, send_fcm):
        """이미 점유된 캠페인은 재전송하지 않고 미래 예약은 건너뜁니다."""
        due = self.campaign()
        future = self.campaign(scheduled_at=timezone.now() + timedelta(minutes=5))
        send_fcm.return_value = (2, 0)

        processed = dispatch_due_marketing_campaigns()

        self.assertEqual([campaign.pk for campaign in processed], [due.pk])
        self.assertIsNone(dispatch_marketing_campaign(due.pk))
        future.refresh_from_db()
        self.assertEqual(future.status, MarketingPushCampaign.Status.SCHEDULED)
        self.assertEqual(send_fcm.call_count, 1)


class MarketingConsentAndDeviceTokenTests(APITestCase):
    """마케팅 동의와 단말 활성 역할 API를 검증합니다."""

    def setUp(self):
        """인증된 테스트 사용자를 준비합니다."""
        self.user = make_user('consent@example.com', marketing_opt_in=False)
        self.client.force_authenticate(self.user)

    def test_marketing_consent_toggle_records_opt_out_and_opt_in_history(self):
        """동의 토글은 현재값과 동의 이력을 함께 갱신합니다."""
        url = '/accounts/me/marketing-consent/'

        enabled = self.client.patch(url, {'marketing_opt_in': True}, format='json')
        disabled = self.client.patch(url, {'marketing_opt_in': False}, format='json')

        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(disabled.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.marketing_opt_in)
        self.assertEqual(
            list(
                UserConsent.objects.filter(user=self.user, doc_type=UserConsent.DOC_MARKETING)
                .order_by('id')
                .values_list('agreed', flat=True)
            ),
            [True, False],
        )

    def test_device_token_accepts_active_role_updates(self):
        """토큰 등록과 갱신 시 단말 활성 역할을 보관합니다."""
        response = self.client.post(
            '/device-token/',
            {'token': 'role-aware-token', 'platform': 'android', 'active_role': 'student'},
            format='json',
        )
        updated = self.client.put('/device-token/', {'active_role': 'instructor'}, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['active_role'], 'instructor')


class MarketingAdminApiTests(APITestCase):
    """슈퍼관리자용 마케팅 템플릿과 캠페인 API를 검증합니다."""

    def setUp(self):
        """일반 사용자와 슈퍼관리자를 준비합니다."""
        self.admin = make_user('marketing-admin@example.com', superuser=True)
        self.user = make_user('marketing-user@example.com')

    def test_template_requires_superuser_and_campaign_can_be_cancelled(self):
        """권한 제한과 예약 캠페인 취소를 검증합니다."""
        template_url = '/admin-api/v1/marketing/templates/'
        self.assertEqual(self.client.get(template_url).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(template_url).status_code, 403)
        self.client.force_authenticate(self.admin)

        template = self.client.post(
            template_url,
            {'name': '주간 혜택', 'title': '이번 주 혜택', 'body': '혜택을 확인해 보세요.'},
            format='json',
        )
        campaign = self.client.post(
            '/admin-api/v1/marketing/campaigns/',
            {
                'target_role': 'student',
                'title': template.data['title'],
                'body': template.data['body'],
                'scheduled_at': (timezone.now() + timedelta(hours=1)).isoformat(),
                'push_only': False,
            },
            format='json',
        )
        cancelled = self.client.post(
            f"/admin-api/v1/marketing/campaigns/{campaign.data['id']}/cancel/",
            format='json',
        )

        self.assertEqual(template.status_code, 201)
        self.assertEqual(campaign.status_code, 201)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data['status'], MarketingPushCampaign.Status.CANCELLED)

    @patch('config.apps.notification.marketing._send_fcm_batches')
    def test_due_macro_creates_one_snapshot_campaign_and_moves_next_schedule(self, send_fcm):
        """기한이 지난 매크로는 한 번만 캠페인 스냅샷으로 만들어 발송합니다."""
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            '/admin-api/v1/marketing/macros/',
            {
                'name': '매일 오전 알림',
                'target_role': 'student',
                'title': '오늘의 소식',
                'body': '새 혜택을 확인해 보세요.',
                'push_only': True,
                'recurrence': 'DAILY',
                'scheduled_time': '09:30:00',
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        macro = MarketingPushMacro.objects.get(pk=created.data['id'])
        macro.next_scheduled_at = timezone.now() - timedelta(minutes=1)
        macro.save(update_fields=['next_scheduled_at'])
        send_fcm.return_value = (0, 0)

        dispatched = dispatch_due_marketing_campaigns()

        self.assertEqual(len(dispatched), 1)
        campaign = dispatched[0]
        self.assertEqual(campaign.macro_id, macro.id)
        self.assertEqual(campaign.title, '오늘의 소식')
        macro.refresh_from_db()
        self.assertGreater(macro.next_scheduled_at, timezone.now())

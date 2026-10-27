"""관리자 마케팅 푸시 API 직렬화기입니다."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from config.apps.notification.models import MarketingPushCampaign, MarketingPushTemplate
from config.apps.notification.marketing import next_macro_occurrence
from config.apps.notification.models import MarketingPushMacro


class MarketingPushTemplateSerializer(serializers.ModelSerializer):
    """마케팅 매크로 템플릿의 생성·수정·조회 계약입니다."""

    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = MarketingPushTemplate
        fields = [
            'id', 'name', 'title', 'body', 'created_by_email', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by_email', 'created_at', 'updated_at']


class MarketingPushCampaignSerializer(serializers.ModelSerializer):
    """마케팅 예약 발송 생성·수정·현황 응답 계약입니다."""

    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    macro_id = serializers.IntegerField(source='macro.id', read_only=True)
    macro_name = serializers.CharField(source='macro.name', read_only=True)
    scheduled_at = serializers.DateTimeField(required=False)

    class Meta:
        model = MarketingPushCampaign
        fields = [
            'id', 'target_role', 'title', 'body', 'scheduled_at', 'push_only',
            'status', 'sent_at', 'recipient_count', 'token_count', 'success_count',
            'failure_count', 'failure_detail', 'created_by_email', 'created_at', 'updated_at',
            'macro_id', 'macro_name',
        ]
        read_only_fields = [
            'id', 'status', 'sent_at', 'recipient_count', 'token_count', 'success_count',
            'failure_count', 'failure_detail', 'created_by_email', 'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        """예약 상태에서만 수정하고 예약 시각이 과거가 아닌지 검증합니다."""
        if self.instance is not None:
            if self.instance.status != MarketingPushCampaign.Status.SCHEDULED:
                raise serializers.ValidationError('예약 상태의 캠페인만 수정할 수 있습니다.')
            return attrs

        scheduled_at = attrs.get('scheduled_at') or timezone.now()
        if scheduled_at < timezone.now() - timedelta(seconds=5):
            raise serializers.ValidationError({'scheduled_at': '발송 시각은 현재 이후여야 합니다.'})
        attrs['scheduled_at'] = scheduled_at
        return attrs


class MarketingPushMacroSerializer(serializers.ModelSerializer):
    """반복 마케팅 발송 매크로의 생성·수정·조회 계약입니다."""

    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = MarketingPushMacro
        fields = [
            'id', 'name', 'target_role', 'title', 'body', 'push_only', 'recurrence',
            'scheduled_time', 'weekday', 'day_of_month', 'next_scheduled_at',
            'last_dispatched_at', 'is_active', 'created_by_email', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'next_scheduled_at', 'last_dispatched_at', 'created_by_email',
            'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        """반복 단위별로 필요한 KST 시·분, 요일 또는 일자를 검증합니다."""
        macro = self.instance
        recurrence = attrs.get('recurrence', getattr(macro, 'recurrence', None))
        weekday = attrs.get('weekday', getattr(macro, 'weekday', None))
        day_of_month = attrs.get('day_of_month', getattr(macro, 'day_of_month', None))

        if recurrence == MarketingPushMacro.Recurrence.WEEKLY:
            if weekday is None or not 0 <= weekday <= 6:
                raise serializers.ValidationError({'weekday': '매주 발송은 월요일(0)부터 일요일(6) 중 요일을 선택해야 합니다.'})
            attrs['day_of_month'] = None
        elif recurrence == MarketingPushMacro.Recurrence.MONTHLY:
            if day_of_month is None or not 1 <= day_of_month <= 31:
                raise serializers.ValidationError({'day_of_month': '매월 발송 일자는 1일부터 31일까지여야 합니다.'})
            attrs['weekday'] = None
        elif recurrence == MarketingPushMacro.Recurrence.DAILY:
            attrs['weekday'] = None
            attrs['day_of_month'] = None
        return attrs

    def create(self, validated_data):
        """생성 직전 KST 현재 시각을 기준으로 다음 실행 시각을 채웁니다."""
        macro = MarketingPushMacro(**validated_data)
        macro.next_scheduled_at = next_macro_occurrence(macro, after=timezone.now())
        macro.save()
        return macro

    def update(self, instance, validated_data):
        """스케줄 변경 또는 재활성화 시 다음 실행 시각을 새로 계산합니다."""
        schedule_fields = {'recurrence', 'scheduled_time', 'weekday', 'day_of_month'}
        reschedule = bool(schedule_fields.intersection(validated_data)) or (
            validated_data.get('is_active') is True and not instance.is_active
        )
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if reschedule:
            instance.next_scheduled_at = next_macro_occurrence(instance, after=timezone.now())
        instance.save()
        return instance

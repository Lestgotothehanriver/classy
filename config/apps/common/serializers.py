class M2MSyncMixin:
    """subjects/regions 등 M2M 필드의 create/update 로직을 통합합니다."""
    m2m_fields = {}  # 예: {'subjects': Subject, 'regions': Region}

    def _sync_m2m_field(self, manager, model_cls, numbers):
        objs = [model_cls.objects.get_or_create(number=n)[0] for n in numbers]
        manager.set(objs)

    def create(self, validated_data):
        m2m_data = {
            field_name: validated_data.pop(field_name, None)
            for field_name in self.m2m_fields.keys()
        }
        instance = super().create(validated_data)
        
        for field_name, model_cls in self.m2m_fields.items():
            data = m2m_data[field_name]
            if data is not None:
                manager = getattr(instance, field_name)
                self._sync_m2m_field(manager, model_cls, data)
                
        return instance

    def update(self, instance, validated_data):
        m2m_data = {
            field_name: validated_data.pop(field_name, None)
            for field_name in self.m2m_fields.keys()
        }
        instance = super().update(instance, validated_data)
        
        for field_name, model_cls in self.m2m_fields.items():
            data = m2m_data[field_name]
            if data is not None:
                manager = getattr(instance, field_name)
                self._sync_m2m_field(manager, model_cls, data)
                
        return instance


from rest_framework import serializers
from config.apps.common.utils import get_absolute_media_url

class AbsoluteFileField(serializers.FileField):
    """
    항상 절대경로 URL을 반환하는 FileField입니다.
    """
    def to_representation(self, value):
        if not value:
            return None
        request = self.context.get('request')
        return get_absolute_media_url(value, request)


class AbsoluteImageField(serializers.ImageField):
    """
    항상 절대경로 URL을 반환하는 ImageField입니다.
    """
    def to_representation(self, value):
        if not value:
            return None
        request = self.context.get('request')
        return get_absolute_media_url(value, request)


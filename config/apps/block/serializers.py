from rest_framework import serializers
from .models import Block
from django.contrib.auth import get_user_model

User = get_user_model()

class BlockSerializer(serializers.ModelSerializer):
    blocked_user_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Block
        fields = ("id", "user", "blocked_user", "blocked_user_info", "created_at")
        read_only_fields = ("user", "created_at")

    def get_blocked_user_info(self, obj):
        user = obj.blocked_user
        profile_image = getattr(user, 'profile_image', None)
        if not profile_image and hasattr(user, 'profile_img'):
            profile_image = user.profile_img

        from config.apps.common.utils import get_absolute_media_url
        profile_img_url = get_absolute_media_url(profile_image, self.context.get('request'))

        return {
            "id": user.id,
            "name": getattr(user, 'user_name', user.username),
            "profile_img": profile_img_url
        }

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("인증되지 않은 사용자입니다.")
            
        user = request.user
        blocked_user = attrs.get("blocked_user")
        
        if user == blocked_user:
            raise serializers.ValidationError("자기 자신을 차단할 수 없습니다.")
            
        return attrs

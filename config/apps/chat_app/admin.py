from django.contrib import admin
from .models import ChatRoom, ChatMessage, Image, UserDeviceToken

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_room_title', 'get_sender_username', 'text', 'created_at')
    list_display_links = ('id', 'text')
    list_filter = ('room__title', 'created_at')
    search_fields = ('text', 'sender__user_name','room__title')
    ordering = ('-created_at',)
    raw_id_fields = ('room', 'sender')

    @admin.display(description='채팅방 제목')
    def get_room_title(self, obj):
        return obj.room.title or f"Room {obj.room.pk}"

    @admin.display(description='발신자')
    def get_sender_username(self, obj):
        return obj.sender.user_name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('room', 'sender')


class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'created_at')
    search_fields = ('title',)
    ordering = ('-created_at',)

admin.site.register(Image)
admin.site.register(UserDeviceToken)
# Register your models here.

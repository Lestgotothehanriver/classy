from django.contrib import admin
from .models import ChatRoom, ChatMessage, Image, UserDeviceToken

class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room_title', 'sender_nickname', 'sender_name', 'text')
    search_fields = ('room_title', 'sender_nickname', 'sender_name')
    ordering = ('-created_at',)

    def sender_nickname(self, obj):
        return obj.sender.user_name 

    def sender_name(self, obj):
        return obj.sender.user_name

    def room_title(self, obj):
        return obj.room.title

class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title',)
    ordering = ('-created_at',)

admin.site.register(ChatRoom, ChatRoomAdmin)
admin.site.register(Image)
admin.site.register(UserDeviceToken)
admin.site.register(ChatMessage, ChatMessageAdmin)
# Register your models here.

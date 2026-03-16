from django.contrib import admin
from .models import ChatSession, ChatMessage

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'session_started', 'session_ended')
    search_fields = ('user_id',)

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'timestamp')
    list_filter = ('role',)
    search_fields = ('content',)

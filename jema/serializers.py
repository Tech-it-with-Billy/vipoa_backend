from rest_framework import serializers
from .models import ChatSession, ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'timestamp']

class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(source='session_started', read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'user_id', 'created_at', 'session_started', 'session_ended', 'messages']

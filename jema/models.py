from django.conf import settings

class ChatSession(models.Model):
    """Stores chat sessions for a user."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
        null=True,  # optional if anonymous sessions are allowed
        blank=True
    )
    session_started = models.DateTimeField(auto_now_add=True)
    session_ended = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Session {self.id} - User {self.user.email if self.user else 'Anonymous'}"

class ChatMessage(models.Model):
    """Stores individual messages in a chat session."""
    session = models.ForeignKey(ChatSession, related_name='messages', on_delete=models.CASCADE)
    role = models.CharField(max_length=50, choices=[('user', 'User'), ('assistant', 'Assistant')])
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role.title()} message in Session {self.session.id}"
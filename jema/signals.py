# jema/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from jema.models import ChatMessage
from rewards.services.events import award_jema_first_interaction
from django.conf import settings

@receiver(post_save, sender=ChatMessage)
def award_first_jema_interaction(sender, instance: ChatMessage, created: bool, **kwargs):
    """
    Trigger reward for first Jema interaction.

    Works with:
    - ChatSession.user_id (Supabase UUID string)
    - SupabaseUser.id (UUID primary key)

    No DB schema changes required.
    """
    if not created:
        return

    if instance.role != "user":
        return

    session = instance.session
    if not session.user_id:
        return

    # -----------------------------
    # Map Supabase sub -> Django user
    # -----------------------------
    try:
        user = User.objects.get(id=session.user_id)
    except User.DoesNotExist:
        return

    # -----------------------------
    # Check if this is first message
    # -----------------------------
    previous_messages_exist = ChatMessage.objects.filter(
        session__user_id=session.user_id,
        role="user"
    ).exclude(id=instance.id).exists()

    if previous_messages_exist:
        return

    # -----------------------------
    # Delegate to rewards app
    # -----------------------------
    award_first_jema_interaction(user=user)
# jema/signals.py
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from jema.models import ChatMessage
from rewards.services.events import award_jema_first_interaction

logger = logging.getLogger(__name__)
User = get_user_model()

@receiver(post_save, sender=ChatMessage)
def award_jema_first_message(sender, instance: ChatMessage, created: bool, **kwargs):
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
        logger.warning("jema.reward_user_not_found session_id=%s user_id=%s", session.id, session.user_id)
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
    try:
        result = award_jema_first_interaction(user=user)
        logger.info(
            "jema.first_interaction_reward user_id=%s session_id=%s outcome=%s",
            user.id,
            session.id,
            result.outcome,
        )
    except Exception:
        logger.exception("jema.first_interaction_reward_failed user_id=%s session_id=%s", user.id, session.id)
        if settings.DEBUG:
            raise
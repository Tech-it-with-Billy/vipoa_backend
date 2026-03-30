from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ChatMessage, ChatSession
from django.contrib.auth import get_user_model
from rewards.services.events import award_first_jema_interaction

User = get_user_model()

@receiver(post_save, sender=ChatMessage)
def trigger_first_jema_interaction(sender, instance: ChatMessage, created, **kwargs):
    if not created:
        return
    if instance.role != "user":
        return

    try:
        user = User.objects.get(id=instance.session.user_id)  # Auth user ID
    except User.DoesNotExist:
        return

    # Delegate to rewards app
    award_first_jema_interaction(user=user)
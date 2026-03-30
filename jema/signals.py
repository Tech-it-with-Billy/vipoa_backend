# jema/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from jema.models import ChatMessage
from rewards.services.events import award_jema_first_interaction
from django.conf import settings

@receiver(post_save, sender=ChatMessage)
def award_first_jema_interaction(sender, instance: ChatMessage, created: bool, **kwargs):
    """
    Awards 50 points to a user the first time they interact with Jema.
    Only triggers if:
      - message role is 'user'
      - the user exists
      - the user has no previous ChatMessage records
    """
    if not created:
        return  # only process newly created messages

    session = instance.session
    user = session.user  # points to real user

    if not user:
        return  # skip if anonymous session

    # Only award if this is the first user message
    previous_messages_exist = ChatMessage.objects.filter(
        session__user=user,
        role='user'
    ).exclude(id=instance.id).exists()

    if not previous_messages_exist:
        # award points via rewards app
        award_jema_first_interaction(user=user)
# accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from rewards.services.wallet import get_or_create_wallet

User = settings.AUTH_USER_MODEL

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        # Only when a new user is created
        get_or_create_wallet(instance)
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from profiles.models import Profile

User = get_user_model()


# Disabled - profile creation is handled in profiles/signals.py
# @receiver(post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     """
#     Automatically create a Profile when a new user is created.
#     Prevents duplicate creation.
#     """
#     if created:
#         Profile.objects.get_or_create(
#             user=instance,
#             defaults={
#                 "name": instance.full_name or "",
#                 "email": instance.email,
#             },
#         )

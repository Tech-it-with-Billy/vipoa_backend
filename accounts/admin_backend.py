# accounts/admin_backend.py

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class SuperUserOnlyBackend(ModelBackend):
    """
    Allows login ONLY for superusers.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(email=username)
        except User.DoesNotExist:
            return None
        
        if user.check_password(password) and user.is_superuser:
            return user
        
        return None

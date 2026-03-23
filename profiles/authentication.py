import logging
from typing import Optional
import requests
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import authentication, exceptions
import jwt

User = get_user_model()
logger = logging.getLogger(__name__)


class SupabaseAuthentication(authentication.BaseAuthentication):
    """
    Authenticate requests using Supabase JWT and ensure
    local user exists (profile/wallet creation handled via signals)
    """

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).split()

        if not auth_header:
            raise exceptions.AuthenticationFailed("Missing Authorization header")

        if len(auth_header) != 2 or auth_header[0].lower() != b"bearer":
            raise exceptions.AuthenticationFailed("Authorization header must be Bearer token")

        token = auth_header[1].decode("utf-8")

        if not token:
            raise exceptions.AuthenticationFailed("Empty bearer token")

        # user_data = self._get_supabase_user(token)
        ################################################################################
        decoded = jwt.decode(token, options={"verify_signature": False})
        user_data = {
            "id": decoded["sub"],
            "email": decoded["email"],
            "user_metadata": decoded.get("user_metadata", {}),
        }
        #################################################################################
        
        if not user_data:
            raise exceptions.AuthenticationFailed("Invalid or expired Supabase token")

        user = self._get_or_create_app_user(user_data)

        # Optional: check profile completion on login
        if hasattr(user, "profile"):
            profile = user.profile
            if profile.is_profile_complete() and not profile.profile_completed_awarded:
                from rewards.services.events import award_profile_completion
                profile.profile_completed_awarded = True
                profile.save(update_fields=["profile_completed_awarded"])
                award_profile_completion(user=user)

        return (user, None)

    def _get_supabase_user(self, token: str) -> Optional[dict]:
        cache_key = f"supabase_user_{token}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        if not settings.SUPABASE_URL:
            raise exceptions.AuthenticationFailed("SUPABASE_URL not configured")

        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            response = requests.get(url, headers=headers, timeout=5)
        except requests.exceptions.RequestException as exc:
            logger.exception("Supabase auth request failed")
            raise exceptions.AuthenticationFailed("Auth server unreachable") from exc

        if response.status_code != 200:
            logger.warning(f"Supabase token invalid: {response.text}")
            raise exceptions.AuthenticationFailed("Invalid Supabase token")

        data = response.json()
        if not data.get("id") or not data.get("email"):
            raise exceptions.AuthenticationFailed("Invalid Supabase payload")

        cache.set(cache_key, data, timeout=60)
        return data

    @transaction.atomic
    def _get_or_create_app_user(self, user_data: dict) -> User:
        uid = user_data["id"]
        email = user_data["email"]
        full_name = user_data.get("user_metadata", {}).get("full_name", "")

        user, created = User.objects.get_or_create(
            id=uid,
            defaults={"email": email, "full_name": full_name, "is_active": True},
        )

        if not created:
            updated = False
            if user.email != email:
                user.email = email
                updated = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated = True
            if updated:
                user.save(update_fields=["email", "full_name"])

        return user
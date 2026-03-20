import logging
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

User = get_user_model()

logger = logging.getLogger(__name__)


class SupabaseAuthentication(authentication.BaseAuthentication):
    """Authenticate requests using Supabase JWT and Supabase /auth/v1/user endpoint."""

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).split()

        if not auth_header:
            raise exceptions.AuthenticationFailed("Missing Authorization header")

        if len(auth_header) != 2 or auth_header[0].lower() != b"bearer":
            raise exceptions.AuthenticationFailed("Authorization header must be Bearer token")

        token = auth_header[1].decode("utf-8")
        if not token:
            raise exceptions.AuthenticationFailed("Empty bearer token")

        user_data = self._get_supabase_user(token)
        if not user_data:
            raise exceptions.AuthenticationFailed("Invalid or expired Supabase token")

        user = self._get_or_create_app_user(user_data)
        return (user, None)

    def _get_supabase_user(self, token: str) -> Optional[dict]:
        cache_key = f"supabase_user_{token}"
        user_data = cache.get(cache_key)
        if user_data is not None:
            return user_data

        supabase_url = settings.SUPABASE_URL.rstrip("/") if settings.SUPABASE_URL else None
        if not supabase_url:
            logger.error("SUPABASE_URL is not configured")
            raise exceptions.AuthenticationFailed("Supabase authentication is not configured")

        url = f"{supabase_url}/auth/v1/user"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=5)
        except requests.exceptions.RequestException as exc:
            logger.exception("Supabase auth endpoint is unavailable")
            raise exceptions.AuthenticationFailed("Error validating authentication token") from exc

        if response.status_code != 200:
            logger.warning("Supabase token validation failed: %s %s", response.status_code, response.text)
            raise exceptions.AuthenticationFailed("Invalid Supabase token")

        user_data = response.json()
        if not user_data.get("id") or not user_data.get("email"):
            logger.warning("Supabase user endpoint returned invalid payload: %s", user_data)
            raise exceptions.AuthenticationFailed("Invalid Supabase user payload")

        cache.set(cache_key, user_data, timeout=60)
        return user_data

    def _get_or_create_app_user(self, user_data: dict) -> User:
        uid = user_data["id"]
        email = user_data["email"]
        full_name = user_data.get("user_metadata", {}).get("full_name", "")

        user, created = User.objects.get_or_create(
            id=uid,
            defaults={
                "email": email,
                "full_name": full_name,
                "is_active": True,
            },
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
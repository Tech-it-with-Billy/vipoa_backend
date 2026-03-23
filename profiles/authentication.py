import logging
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import authentication, exceptions

User = get_user_model()

logger = logging.getLogger(__name__)


class SupabaseAuthentication(authentication.BaseAuthentication):
    """
    Authenticate requests using Supabase JWT and ensure
    local user + profile + wallet exist.
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

        user_data = self._get_supabase_user(token)

        if not user_data:
            raise exceptions.AuthenticationFailed("Invalid or expired Supabase token")

        user = self._get_or_create_app_user(user_data)

        return (user, None)

    # ------------------------------------------------------------------
    # SUPABASE USER FETCH
    # ------------------------------------------------------------------
    def _get_supabase_user(self, token: str) -> Optional[dict]:
        cache_key = f"supabase_user_{token}"
        cached = cache.get(cache_key)

        if cached:
            return cached

        if not settings.SUPABASE_URL:
            raise exceptions.AuthenticationFailed("SUPABASE_URL not configured")

        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

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

    # ------------------------------------------------------------------
    # USER + PROFILE + WALLET CREATION (CRITICAL FIX)
    # ------------------------------------------------------------------
    @transaction.atomic
    def _get_or_create_app_user(self, user_data: dict) -> User:
        """
        Ensures:
        - User exists
        - Profile exists
        - Wallet exists
        """

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

        # -----------------------------
        # UPDATE USER IF EXISTS
        # -----------------------------
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

        # -----------------------------
        # ENSURE PROFILE EXISTS
        # -----------------------------
        from profiles.models import Profile

        Profile.objects.get_or_create(
            user=user,
            defaults={
                "email": email,
                "name": full_name,
            },
        )

        # -----------------------------
        # ENSURE WALLET EXISTS
        # -----------------------------
        try:
            from rewards.models import POAWallet

            POAWallet.objects.get_or_create(
                user=user,
                defaults={
                    "balance": 0
                }
            )
        except Exception as e:
            logger.warning(f"Wallet creation failed: {e}")

        return user
import logging
import hashlib
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import authentication, exceptions

from jose import jwt
from jose.exceptions import JWTError

User = get_user_model()
logger = logging.getLogger(__name__)


class SupabaseAuthentication(authentication.BaseAuthentication):
    """
    Production-grade Supabase JWT authentication using JWKS (no API calls)
    """

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).split()

        if not auth_header:
            return None

        if len(auth_header) != 2 or auth_header[0].lower() != b"bearer":
            return None

        token = auth_header[1].decode("utf-8")

        if not token:
            raise exceptions.AuthenticationFailed("Empty token")

        user_data = self._verify_jwt(token)

        user = self._get_or_create_user(user_data)
        
        logger.info(f"AUTH HEADER: {auth_header}")
        logger.info(f"USER DATA: {user_data}")
        logger.info("🔥 AUTHENTICATION RUNNING")

        return (user, None)

    # ------------------------------------------------------------------
    # VERIFY JWT USING SUPABASE JWKS
    # ------------------------------------------------------------------
    def _verify_jwt(self, token: str) -> dict:
        try:
            # Decode header to get key id (kid)
            headers = jwt.get_unverified_header(token)
            kid = headers.get("kid")

            if not kid:
                raise exceptions.AuthenticationFailed("Invalid token header")

            # Fetch JWKS (cached)
            jwks = self._get_jwks()

            key = next((k for k in jwks["keys"] if k["kid"] == kid), None)

            if not key:
                raise exceptions.AuthenticationFailed("Public key not found")

            # Verify token
            payload = jwt.decode(
                token,
                key,
                algorithms=["ES256"],
                audience=settings.SUPABASE_AUDIENCE,
                issuer=f"{settings.SUPABASE_URL}/auth/v1",
            )

            return payload

        except JWTError as e:
            logger.warning(f"JWT verification failed: {str(e)}")
            raise exceptions.AuthenticationFailed("Invalid or expired token")

    # ------------------------------------------------------------------
    # FETCH JWKS (WITH CACHE)
    # ------------------------------------------------------------------
    def _get_jwks(self) -> dict:
        cache_key = "supabase_jwks"
        jwks = cache.get(cache_key)

        if jwks:
            return jwks

        try:
            response = requests.get(settings.SUPABASE_JWKS_URL, timeout=5)
            response.raise_for_status()
            jwks = response.json()

            cache.set(cache_key, jwks, timeout=3600)  # cache 1 hour

            return jwks

        except Exception as e:
            logger.exception("Failed to fetch JWKS")
            raise exceptions.AuthenticationFailed("Auth server error")

    # ------------------------------------------------------------------
    # USER CREATION
    # ------------------------------------------------------------------
    @transaction.atomic
    def _get_or_create_user(self, payload: dict) -> User:
        uid = payload["sub"]
        email = payload.get("email", "")
        full_name = payload.get("user_metadata", {}).get("full_name", "")

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

            if email and user.email != email:
                user.email = email
                updated = True

            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated = True

            if updated:
                user.save(update_fields=["email", "full_name"])

        # Ensure Profile + Wallet
        from profiles.models import Profile
        from rewards.models.wallet import PoaPointsAccount

        Profile.objects.get_or_create(
            user=user,
            defaults={"email": email, "name": full_name},
        )

        PoaPointsAccount.objects.get_or_create(
            user=user,
            defaults={"balance": 0},
        )
        
        logger.info("🔥 USER CREATION RUNNING")

        return user
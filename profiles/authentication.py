import logging
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

from jose import jwt
from jose.exceptions import JWTError

from django.db import transaction, IntegrityError

User = get_user_model()
logger = logging.getLogger(__name__)


class SupabaseAuthentication(authentication.BaseAuthentication):
    """
    Supabase JWT authentication using JWKS (no API calls to user DB)
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

        payload = self._verify_jwt(token)
        user = self._get_or_create_user(payload)

        logger.info(f"AUTH HEADER: {auth_header}")
        logger.info(f"USER DATA: {payload}")
        logger.info("🔥 AUTHENTICATION RUNNING")

        return (user, None)

    # -----------------------------
    # VERIFY JWT USING SUPABASE JWKS
    # -----------------------------
    def _verify_jwt(self, token: str) -> dict:
        try:
            headers = jwt.get_unverified_header(token)
            kid = headers.get("kid")
            if not kid:
                raise exceptions.AuthenticationFailed("Invalid token header")

            jwks = self._get_jwks()
            key = next((k for k in jwks["keys"] if k["kid"] == kid), None)

            if not key:
                raise exceptions.AuthenticationFailed("Public key not found")

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

    # -----------------------------
    # FETCH JWKS WITH CACHE
    # -----------------------------
    def _get_jwks(self) -> dict:
        cache_key = "supabase_jwks"
        jwks = cache.get(cache_key)
        if jwks:
            return jwks

        try:
            response = requests.get(settings.SUPABASE_JWKS_URL, timeout=5)
            response.raise_for_status()
            jwks = response.json()
            cache.set(cache_key, jwks, timeout=3600)
            return jwks
        except Exception as e:
            logger.exception("Failed to fetch JWKS")
            raise exceptions.AuthenticationFailed("Auth server error")

    # -----------------------------
    # GET OR CREATE USER (without creating Profile or Wallet)
    # -----------------------------
    @transaction.atomic
    def _get_or_create_user(self, payload: dict) -> User:
        """
        Safely get or create a SupabaseUser based on JWT payload.
        Ensures:
        - Email uniqueness
        - Profile and PoaPointsAccount exist
        """
        uid = payload["sub"]
        email = payload.get("email", "").lower()
        full_name = payload.get("user_metadata", {}).get("full_name", "")

        # Try to find by UID first
        user = User.objects.filter(id=uid).first()

        if not user:
            # If UID doesn't exist, try to find by email (enforce unique)
            user = User.objects.filter(email=email).first()

        if user:
            # Update info if changed
            updated_fields = []
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated_fields.append("full_name")
            if user.email != email:
                user.email = email
                updated_fields.append("email")
            if updated_fields:
                user.save(update_fields=updated_fields)
        else:
            # Create user safely, handle race condition
            try:
                user = User.objects.create(
                    id=uid,
                    email=email,
                    full_name=full_name,
                    is_active=True,
                )
            except IntegrityError:
                # Likely another process created it concurrently
                user = User.objects.get(email=email)

        # Ensure Profile exists
        from profiles.models import Profile
        Profile.objects.get_or_create(
            user=user,
            defaults={"name": full_name, "email": email},
        )

        # Ensure PoaPointsAccount exists
        from rewards.models.wallet import PoaPointsAccount
        PoaPointsAccount.objects.get_or_create(
            user=user,
            defaults={"balance": 0},
        )

        return user
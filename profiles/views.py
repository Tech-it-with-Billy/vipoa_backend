import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.contrib.auth import get_user_model
from .models import Profile, Referral
from .constants import PROFILE_COMPLETION_FIELDS
from .serializers import (
    ProfileReadSerializer,
    ProfileUpdateSerializer,
    ProfileCompletionStatusSerializer,
    ReferralLeaderboardSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _mask_referral_code(code: str) -> str:
    if not code:
        return ""
    if len(code) <= 6:
        return code
    return f"{code[:4]}...{code[-2:]}"


def _extract_referred_by_code(payload) -> str:
    return (
        payload.get("referred_by")
        or payload.get("referral_code")
        or ""
    ).strip().upper()


# -----------------------------
# REFERRAL HELPER
# -----------------------------
def _process_referred_by(user, profile, code: str):
    """
    Process a referral code submitted during initial profile setup.
    - Silently skips if code is invalid, self-referral, or referral already exists.
    - Creates the Referral record (reward signal fires automatically).
    - Stores the code in profile.referred_by so it is only processed once.
    """
    try:
        referrer_profile = Profile.objects.get(referral_code__iexact=code)
    except Profile.DoesNotExist:
        logger.warning("referral.invalid_code user_id=%s code=%s", user.id, code)
        return

    if referrer_profile.user_id == user.pk:
        logger.warning("referral.self_referral user_id=%s", user.id)
        return

    if Referral.objects.filter(referred_user=user).exists():
        return

    try:
        with transaction.atomic():
            # Re-check inside the lock to prevent race conditions.
            if Referral.objects.filter(referred_user=user).exists():
                return
            referral = Referral.objects.create(referrer=referrer_profile.user, referred_user=user)
            # Write referred_by INSIDE the same atomic block so it rolls back
            # together with the Referral row if anything goes wrong.
            Profile.objects.filter(pk=profile.pk).update(referred_by=code.upper())
            profile.referred_by = code.upper()
            logger.info(
                "referral.applied user_id=%s referrer_user_id=%s code=%s",
                user.id, referrer_profile.user_id, code,
            )
            # Fire reward processing only AFTER the transaction successfully
            # commits — prevents points being awarded on a rolled-back referral.
            referral_id = referral.pk
            referrer_user_id = referrer_profile.user_id

            def _award_on_commit():
                from .referral_rewards import process_referral_rewards
                from django.contrib.auth import get_user_model as _get_user_model
                _User = _get_user_model()
                try:
                    referrer = _User.objects.get(pk=referrer_user_id)
                    total = referrer.referrals_made.count()
                    results = process_referral_rewards(referrer_user=referrer, referral_count=total)
                    awarded = any(
                        getattr(r, "outcome", None) in ("APPLIED", "awarded", True)
                        for _, r in (results or [])
                    )
                    if awarded:
                        Referral.objects.filter(pk=referral_id).update(reward_granted=True)
                    logger.info(
                        "referral.reward_on_commit referral_id=%s awarded=%s",
                        referral_id, awarded,
                    )
                except Exception:
                    logger.exception("referral.reward_on_commit_failure referral_id=%s", referral_id)

            transaction.on_commit(_award_on_commit)

    except IntegrityError:
        logger.warning("referral.integrity_error user_id=%s code=%s", user.id, code)


# -----------------------------
# PROFILE ENDPOINTS
# -----------------------------
class ProfileMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ProfileReadSerializer(request.user.profile).data)

    def patch(self, request):
        profile = request.user.profile
        referred_by_code = _extract_referred_by_code(request.data)
        logger.info(
            "referral.patch_received path=%s user_id=%s has_referred_by=%s has_referral_code=%s code=%s existing_referred_by=%s",
            request.path,
            request.user.id,
            bool(request.data.get("referred_by")),
            bool(request.data.get("referral_code")),
            _mask_referral_code(referred_by_code),
            bool(profile.referred_by),
        )
        data = {
            k: v
            for k, v in request.data.items()
            if k not in {"referred_by", "referral_code"}
        }

        serializer = ProfileUpdateSerializer(profile, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        if referred_by_code and not profile.referred_by:
            _process_referred_by(request.user, profile, referred_by_code)

        profile.refresh_from_db()
        logger.info(
            "referral.patch_completed path=%s user_id=%s stored_referred_by=%s referral_exists=%s",
            request.path,
            request.user.id,
            _mask_referral_code(profile.referred_by),
            Referral.objects.filter(referred_user=request.user).exists(),
        )

        return Response(ProfileReadSerializer(profile).data)


class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        profile = request.user.profile
        referred_by_code = _extract_referred_by_code(request.data)
        logger.info(
            "referral.patch_received path=%s user_id=%s has_referred_by=%s has_referral_code=%s code=%s existing_referred_by=%s",
            request.path,
            request.user.id,
            bool(request.data.get("referred_by")),
            bool(request.data.get("referral_code")),
            _mask_referral_code(referred_by_code),
            bool(profile.referred_by),
        )
        data = {
            k: v
            for k, v in request.data.items()
            if k not in {"referred_by", "referral_code"}
        }

        serializer = ProfileUpdateSerializer(profile, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        if referred_by_code and not profile.referred_by:
            _process_referred_by(request.user, profile, referred_by_code)

        profile.refresh_from_db()
        logger.info(
            "referral.patch_completed path=%s user_id=%s stored_referred_by=%s referral_exists=%s",
            request.path,
            request.user.id,
            _mask_referral_code(profile.referred_by),
            Referral.objects.filter(referred_user=request.user).exists(),
        )

        return Response(ProfileReadSerializer(profile).data)

    def put(self, request):
        return self.patch(request)


class ProfileCompletionStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        missing = profile.missing_completion_fields()
        completed = len(PROFILE_COMPLETION_FIELDS) - len(missing)
        total = len(PROFILE_COMPLETION_FIELDS)
        data = {
            "is_complete": len(missing) == 0,
            "missing_fields": missing,
            "completion_percentage": round(completed / total, 2),
        }
        return Response(ProfileCompletionStatusSerializer(data).data)


# -----------------------------
# REFERRAL ENDPOINTS
# -----------------------------
class ReferralCreateView(APIView):
    """
    POST /api/profiles/referral/create/
    Body: {"referral_code": "<code>"}

    Called by the Flutter client after login/signup to register that the
    current user was referred by someone. Idempotent — safe to call more
    than once; duplicates are silently ignored.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get("referral_code") or "").strip().upper()
        logger.info(
            "referral.create_received path=%s user_id=%s has_code=%s code=%s",
            request.path,
            request.user.id,
            bool(code),
            _mask_referral_code(code),
        )
        if not code:
            return Response({"detail": "referral_code is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        profile = user.profile

        # Already used a referral code before → reject
        if profile.referred_by:
            return Response({"detail": "Referral already applied."}, status=status.HTTP_400_BAD_REQUEST)

        # Referral row already exists for this user → reject
        if Referral.objects.filter(referred_user=user).exists():
            return Response({"detail": "Referral already applied."}, status=status.HTTP_400_BAD_REQUEST)

        _process_referred_by(user, profile, code)

        # Check whether it actually landed (helpers swallows invalid codes silently)
        profile.refresh_from_db()
        if profile.referred_by:
            logger.info(
                "referral.create_completed path=%s user_id=%s stored_referred_by=%s",
                request.path,
                request.user.id,
                _mask_referral_code(profile.referred_by),
            )
            return Response({"detail": "Referral applied successfully."}, status=status.HTTP_201_CREATED)

        logger.info(
            "referral.create_completed path=%s user_id=%s stored_referred_by=%s",
            request.path,
            request.user.id,
            _mask_referral_code(profile.referred_by),
        )
        return Response({"detail": "Invalid or unrecognised referral code."}, status=status.HTTP_400_BAD_REQUEST)


class ReferralCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = request.user.referrals_made.count()
        return Response({"referral_count": count})


class ReferralLeaderboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        leaderboard = (
            Profile.objects.annotate(referral_count=Count("user__referrals_made", distinct=True))
            .order_by("-referral_count")[:10]
        )
        serializer = ReferralLeaderboardSerializer(leaderboard, many=True)
        return Response(serializer.data)

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
            if Referral.objects.filter(referred_user=user).exists():
                return
            Referral.objects.create(referrer=referrer_profile.user, referred_user=user)
        Profile.objects.filter(pk=profile.pk).update(referred_by=code.upper())
        profile.referred_by = code.upper()
        logger.info("referral.applied user_id=%s referrer_user_id=%s code=%s", user.id, referrer_profile.user_id, code)
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
        referred_by_code = (request.data.get("referred_by") or "").strip().upper()
        data = {k: v for k, v in request.data.items() if k != "referred_by"}

        serializer = ProfileUpdateSerializer(profile, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        if referred_by_code and not profile.referred_by:
            _process_referred_by(request.user, profile, referred_by_code)

        return Response(ProfileReadSerializer(profile).data)


class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        profile = request.user.profile
        referred_by_code = (request.data.get("referred_by") or "").strip().upper()
        data = {k: v for k, v in request.data.items() if k != "referred_by"}

        serializer = ProfileUpdateSerializer(profile, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        if referred_by_code and not profile.referred_by:
            _process_referred_by(request.user, profile, referred_by_code)

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

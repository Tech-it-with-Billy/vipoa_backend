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
    ReferralSerializer,
    ReferralLeaderboardSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# -----------------------------
# PROFILE ENDPOINTS
# -----------------------------
class ProfileMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ProfileReadSerializer(request.user.profile).data)

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()
        return Response(ProfileReadSerializer(profile).data)


class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()
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
    Submit a referral code when a new user signs up via a shared link.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        referral_code = (request.data.get("referral_code") or "").strip().upper()
        if not referral_code:
            return Response({"error": "Referral code is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            referrer_profile = Profile.objects.get(referral_code=referral_code)
        except Profile.DoesNotExist:
            return Response({"error": "Invalid referral code."}, status=status.HTTP_404_NOT_FOUND)

        # Prevent self-referral
        if referrer_profile.user == request.user:
            return Response({"error": "Cannot refer yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent duplicate referrals for the same user
        if Referral.objects.filter(referred_user=request.user).exists():
            return Response({"error": "Referral already applied."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Serialize requests for the same referred user to avoid races.
                User.objects.select_for_update().get(pk=request.user.pk)

                if Referral.objects.filter(referred_user=request.user).exists():
                    return Response({"error": "Referral already applied."}, status=status.HTTP_400_BAD_REQUEST)

                referral = Referral.objects.create(
                    referrer=referrer_profile.user,
                    referred_user=request.user,
                )
        except IntegrityError:
            logger.warning(
                "referral.create_integrity_error user_id=%s referrer_user_id=%s code=%s",
                request.user.id,
                referrer_profile.user_id,
                referral_code,
            )
            return Response({"error": "Referral already applied."}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            "referral.create_success user_id=%s referrer_user_id=%s referral_id=%s",
            request.user.id,
            referrer_profile.user_id,
            referral.id,
        )

        serializer = ReferralSerializer(referral)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReferralCountView(APIView):
    """
    Return the number of referrals made by the current user
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = request.user.referrals_made.count()
        return Response({"referral_count": count})


class ReferralLeaderboardView(APIView):
    """
    Return top referrers sorted by referral count
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        leaderboard = (
            Profile.objects.annotate(referral_count=Count("user__referrals_made", distinct=True))
            .order_by("-referral_count")[:10]
        )
        serializer = ReferralLeaderboardSerializer(leaderboard, many=True)
        return Response(serializer.data)
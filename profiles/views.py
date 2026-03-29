from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Count
from .models import Profile, Referral
from .constants import PROFILE_COMPLETION_FIELDS
from .serializers import (
    ProfileReadSerializer,
    ProfileUpdateSerializer,
    ProfileCompletionStatusSerializer,
    ReferralSerializer,
    ReferralLeaderboardSerializer,
)


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
        referral_code = request.data.get("referral_code")
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

        referral = Referral.objects.create(
            referrer=referrer_profile,
            referred_user=request.user
        )

        serializer = ReferralSerializer(referral)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReferralCountView(APIView):
    """
    Return the number of referrals made by the current user
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Referral.objects.filter(referrer=request.user.profile).count()
        return Response({"referral_count": count})


class ReferralLeaderboardView(APIView):
    """
    Return top referrers sorted by referral count
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        leaderboard = (
            Profile.objects.annotate(referral_count=Count("referrals"))
            .order_by("-referral_count")[:10]
        )
        serializer = ReferralLeaderboardSerializer(leaderboard, many=True)
        return Response(serializer.data)
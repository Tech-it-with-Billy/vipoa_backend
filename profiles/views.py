from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Profile, PROFILE_COMPLETION_FIELDS
from .serializers import (
    ProfileReadSerializer,
    ProfileUpdateSerializer,
    ProfileCompletionStatusSerializer,
)

# Rewards engine (single source of truth)
from rewards.services.events import award_profile_completion


# --------------------------------------------------
# PROFILE: GET + UPDATE CURRENT USER PROFILE
# --------------------------------------------------
class ProfileMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            ProfileReadSerializer(request.user.profile).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        profile = request.user.profile

        serializer = ProfileUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        profile.refresh_from_db()

        # Award points if eligible
        result = award_profile_completion(user=request.user)

        # If profile is now complete and not already marked as awarded, update flag and sync poa_points
        if profile.is_profile_complete() and not profile.profile_completed_awarded:
            # Try to get wallet balance
            try:
                wallet = getattr(request.user, "poa_wallet", None)
                if wallet:
                    profile.poa_points = wallet.balance
            except Exception:
                pass
            profile.profile_completed_awarded = True
            profile.save(update_fields=["profile_completed_awarded", "poa_points"])

        return Response(
            ProfileReadSerializer(profile).data,
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------
# PROFILE COMPLETION STATUS (CRITICAL DEBUG ENDPOINT)
# --------------------------------------------------
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

        return Response(
            ProfileCompletionStatusSerializer(data).data,
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------
# LEGACY UPDATE VIEW (BACKWARD COMPAT)
# --------------------------------------------------
class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        result = award_profile_completion(user=request.user)

        if profile.is_profile_complete() and not profile.profile_completed_awarded:
            try:
                wallet = getattr(request.user, "poa_wallet", None)
                if wallet:
                    profile.poa_points = wallet.balance
            except Exception:
                pass
            profile.profile_completed_awarded = True
            profile.save(update_fields=["profile_completed_awarded", "poa_points"])

        return Response(ProfileReadSerializer(profile).data, status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)

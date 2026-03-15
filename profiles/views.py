from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import Profile
from .serializers import ProfileSerializer, ProfileUpdateSerializer, ProfileCompletionStatusSerializer
from rewards.services.events import award_profile_completion

class ProfileMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user.profile).data)

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        # Auto-award points if profile is complete
        if profile.is_profile_complete() and not profile.profile_completed_awarded:
            profile.profile_completed_awarded = True
            profile.save(update_fields=["profile_completed_awarded"])
            award_profile_completion(user=request.user)

        return Response(ProfileSerializer(profile).data)


class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()

        # Auto-award points if profile is complete
        if profile.is_profile_complete() and not profile.profile_completed_awarded:
            profile.profile_completed_awarded = True
            profile.save(update_fields=["profile_completed_awarded"])
            award_profile_completion(user=request.user)

        return Response(ProfileSerializer(profile).data)

    def put(self, request):
        return self.patch(request)


class ProfileCompletionStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = request.user.profile
        missing = profile.missing_completion_fields()
        completed = len(PROFILE_COMPLETION_FIELDS) - len(missing)
        data = {
            "is_complete": len(missing) == 0,
            "missing_fields": missing,
            "completion_percentage": round(completed / len(PROFILE_COMPLETION_FIELDS), 2),
        }
        return Response(ProfileCompletionStatusSerializer(data).data)
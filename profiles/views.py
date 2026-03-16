from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import Profile
from .constants import PROFILE_COMPLETION_FIELDS
from .serializers import (
    ProfileReadSerializer,
    ProfileUpdateSerializer,
    ProfileCompletionStatusSerializer,
)


class ProfileMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ProfileReadSerializer(request.user.profile).data, status=status.HTTP_200_OK)

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()
        return Response(ProfileReadSerializer(profile).data, status=status.HTTP_200_OK)


class ProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        profile = request.user.profile
        serializer = ProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        profile.refresh_from_db()
        return Response(ProfileReadSerializer(profile).data, status=status.HTTP_200_OK)

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

        return Response(ProfileCompletionStatusSerializer(data).data, status=status.HTTP_200_OK)
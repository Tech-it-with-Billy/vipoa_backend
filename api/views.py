# api/views.py

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from django.contrib.auth import get_user_model
from profiles.models import Profile

User = get_user_model()


# -----------------------------------------
# GET USER PROFILE
# -----------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_profile(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    profile, created = Profile.objects.get_or_create(user=user)

    return Response({
        "id": user.id,
        "email": user.email,
        "name": profile.name,
        "gender": profile.gender,
        "dob": profile.dob,
        "location": profile.location,
        "weight": profile.weight,
        "diet": profile.diet,
        "religion": profile.religion,
        "occupational_status": profile.occupational_status,
        "works_at": profile.works_at,
        "income_level": profile.income_level,
        "region": profile.region,
        "poa_points": profile.poa_points,
        "day_streak": profile.day_streak,
    })
    

# -----------------------------------------
# UPDATE USER PROFILE (PATCH)
# -----------------------------------------
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def update_user_profile(request):
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)

    data = request.data

    # Map Flutter Keys → Django Field Names
    update_map = {
        "name": "name",
        "gender": "gender",
        "dob": "dob",
        "location": "location",
        "weight": "weight",
        "diet": "diet",
        "religion": "religion",
        "occupationalStatus": "occupational_status",
        "worksAt": "works_at",
        "incomeLevel": "income_level",
        "region": "region",
    }

    for incoming_key, model_field in update_map.items():
        if incoming_key in data:
            setattr(profile, model_field, data.get(incoming_key, ""))

    profile.save()

    return Response({
        "message": "Profile updated successfully!",
        "profile": {
            "name": profile.name,
            "gender": profile.gender,
            "dob": profile.dob,
            "location": profile.location,
            "weight": profile.weight,
            "diet": profile.diet,
            "religion": profile.religion,
            "occupational_status": profile.occupational_status,
            "works_at": profile.works_at,
            "income_level": profile.income_level,
            "region": profile.region,
        }
    })

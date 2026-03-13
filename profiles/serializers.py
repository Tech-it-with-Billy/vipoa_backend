from rest_framework import serializers
from .models import Profile, PROFILE_COMPLETION_FIELDS

PROFILE_FIELDS = [
    "name",
    "email",
    "gender",
    "dob",
    "location",
    "current_weight_kg",
    "current_height_cm",
    "target_weight_kg",
    "target_height_cm",
    "goal",
    "activity_level",
    "eating_realities",
    "medical_restrictions",
    "allergies",
    "dislikes",
    "cooking_skills",
    "diet",
    "religion",
    "occupational_status",
    "works_at",
    "income_level",
    "region",
]


class ProfileReadSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    poa_points = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    bmi = serializers.SerializerMethodField()
    bmi_category = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            ["id"]
            + PROFILE_FIELDS
            + [
                "poa_points",
                "day_streak",
                "profile_completed_awarded",
                "age",
                "bmi",
                "bmi_category",
                "updated_at",
            ]
        )
        read_only_fields = fields

    def get_poa_points(self, obj):
        wallet = getattr(obj.user, "poa_wallet", None)
        return wallet.balance if wallet else 0

    def get_age(self, obj):
        return obj.age

    def get_bmi(self, obj):
        return obj.bmi

    def get_bmi_category(self, obj):
        return obj.bmi_category


class ProfileUpdateSerializer(serializers.ModelSerializer):
    dob = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Profile
        fields = PROFILE_FIELDS


class ProfileCompletionStatusSerializer(serializers.Serializer):
    is_complete = serializers.BooleanField()
    missing_fields = serializers.ListField(child=serializers.CharField())
    completion_percentage = serializers.FloatField()

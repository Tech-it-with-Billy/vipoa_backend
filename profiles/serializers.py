from rest_framework import serializers
from .models import Profile
from .constants import PROFILE_COMPLETION_FIELDS

class ProfileSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()
    bmi = serializers.SerializerMethodField()
    bmi_category = serializers.SerializerMethodField()
    tdee = serializers.SerializerMethodField()
    poa_points = serializers.SerializerMethodField()
    profile_completed_awarded = serializers.BooleanField(read_only=True)

    class Meta:
        model = Profile
        fields = "__all__"

    def get_age(self, obj):
        return obj.age

    def get_bmi(self, obj):
        return obj.bmi

    def get_bmi_category(self, obj):
        return obj.bmi_category

    def get_tdee(self, obj):
        return obj.tdee

    def get_poa_points(self, obj):
        return obj.poa_points


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        exclude = [
            "user",
            "day_streak",
            "profile_completed_awarded",
            "updated_at",
        ]


class ProfileCompletionStatusSerializer(serializers.Serializer):
    is_complete = serializers.BooleanField()
    missing_fields = serializers.ListField(child=serializers.CharField())
    completion_percentage = serializers.FloatField()
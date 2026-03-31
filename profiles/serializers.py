from rest_framework import serializers
from .models import Profile, Referral
from .constants import PROFILE_COMPLETION_FIELDS
from rewards.services.events import award_profile_completion


# -----------------------------
# Profile Serializers
# -----------------------------
class ProfileReadSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()
    bmi = serializers.SerializerMethodField()
    bmi_category = serializers.SerializerMethodField()
    tdee = serializers.SerializerMethodField()
    poa_points = serializers.SerializerMethodField()
    profile_completed_awarded = serializers.BooleanField(read_only=True)
    referral_code = serializers.CharField(read_only=True)

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
            "referral_code",
                "referred_by",
        ]

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        if instance.is_profile_complete() and not instance.profile_completed_awarded:
            award_profile_completion(user=instance.user)
            instance.profile_completed_awarded = True
            instance.save(update_fields=["profile_completed_awarded"])
        return instance


class ProfileCompletionStatusSerializer(serializers.Serializer):
    is_complete = serializers.BooleanField()
    missing_fields = serializers.ListField(child=serializers.CharField())
    completion_percentage = serializers.FloatField()


# -----------------------------
# Referral Serializers
# -----------------------------
class ReferralSerializer(serializers.ModelSerializer):
    referrer_email = serializers.CharField(source="referrer.email", read_only=True)
    referred_email = serializers.CharField(source="referred_user.email", read_only=True)

    class Meta:
        model = Referral
        fields = ["id", "referrer_email", "referred_email", "created_at"]


class ReferralCountSerializer(serializers.Serializer):
    referral_count = serializers.SerializerMethodField()

    def get_referral_count(self, obj):
        return Referral.objects.filter(referrer=obj.user).count()


class ReferralLeaderboardSerializer(serializers.ModelSerializer):
    referral_count = serializers.IntegerField()

    class Meta:
        model = Profile
        fields = ["user", "name", "referral_count"]
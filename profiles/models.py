from django.db import models
from django.contrib.auth import get_user_model
from datetime import date
from .constants import PROFILE_COMPLETION_FIELDS

User = get_user_model()


def profile_avatar_upload_path(instance, filename: str) -> str:
    return f"profiles/{instance.user_id}/avatar/{filename}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # -----------------------------
    # BASIC INFO
    # -----------------------------
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=50, blank=True)
    dob = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)

    # -----------------------------
    # HEALTH METRICS
    # -----------------------------
    current_weight_kg = models.FloatField(null=True, blank=True)
    current_height_cm = models.FloatField(null=True, blank=True)
    target_weight_kg = models.FloatField(null=True, blank=True)
    target_height_cm = models.FloatField(null=True, blank=True)
    goal = models.CharField(max_length=100, blank=True)
    activity_level = models.CharField(max_length=50, blank=True)
    eating_realities = models.TextField(blank=True)
    medical_restrictions = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    dislikes = models.TextField(blank=True)
    cooking_skills = models.CharField(max_length=100, blank=True)

    # -----------------------------
    # LIFESTYLE
    # -----------------------------
    diet = models.CharField(max_length=100, blank=True)
    religion = models.CharField(max_length=100, blank=True)
    occupational_status = models.CharField(max_length=100, blank=True)
    works_at = models.CharField(max_length=255, blank=True)
    income_level = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    # -----------------------------
    # GAMIFICATION
    # -----------------------------
    day_streak = models.IntegerField(default=0)
    profile_completed_awarded = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    # -----------------------------
    # WALLET BALANCE
    # -----------------------------
    @property
    def poa_points(self):
        try:
            return self.user.poa_wallet.balance
        except Exception:
            return 0

    # -----------------------------
    # AGE
    # -----------------------------
    @property
    def age(self):
        if not self.dob:
            return None
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    # -----------------------------
    # BMI
    # -----------------------------
    @property
    def bmi(self):
        if not self.current_weight_kg or not self.current_height_cm:
            return None
        height_m = self.current_height_cm / 100
        return round(self.current_weight_kg / (height_m ** 2), 2)

    # -----------------------------
    # BMI CATEGORY
    # -----------------------------
    @property
    def bmi_category(self):
        bmi = self.bmi
        if bmi is None:
            return None
        if bmi < 18.5:
            return "Underweight"
        if bmi < 25:
            return "Normal"
        if bmi < 30:
            return "Overweight"
        return "Obese"

    # -----------------------------
    # BMR
    # -----------------------------
    @property
    def bmr(self):
        if not self.current_weight_kg or not self.current_height_cm or not self.age:
            return None
        if self.gender.lower() == "male":
            return 10 * self.current_weight_kg + 6.25 * self.current_height_cm - 5 * self.age + 5
        return 10 * self.current_weight_kg + 6.25 * self.current_height_cm - 5 * self.age - 161

    # -----------------------------
    # TDEE
    # -----------------------------
    @property
    def tdee(self):
        bmr = self.bmr
        if not bmr:
            return None
        activity_multipliers = {
            "sedentary": 1.2,
            "light": 1.375,
            "moderate": 1.55,
            "very_active": 1.725,
        }
        multiplier = activity_multipliers.get(self.activity_level.lower() if self.activity_level else "", 1.2)
        return round(bmr * multiplier)

    # -----------------------------
    # PROFILE COMPLETION
    # -----------------------------
    def missing_completion_fields(self):
        missing = []
        for field in PROFILE_COMPLETION_FIELDS:
            value = getattr(self, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
        return missing

    def is_profile_complete(self):
        return len(self.missing_completion_fields()) == 0

    def __str__(self):
        return f"Profile(user_id={self.user_id})"
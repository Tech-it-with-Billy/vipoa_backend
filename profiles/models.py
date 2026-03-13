from django.db import models
from django.contrib.auth import get_user_model
from datetime import date

User = get_user_model()


def profile_avatar_upload_path(instance, filename: str) -> str:
    return f"profiles/{instance.user_id}/avatar/{filename}"




PROFILE_COMPLETION_FIELDS = [
    "gender",
    "dob",
    "location",
    "current_weight_kg",
    "current_height_cm",
    "diet",
    "religion",
    "occupational_status",
    "works_at",
    "income_level",
    "region",
]


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

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
    poa_points = models.IntegerField(default=0)
    day_streak = models.IntegerField(default=0)
    profile_completed_awarded = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    # -----------------------------
    # PROFILE COMPLETION LOGIC
    # -----------------------------
    def missing_completion_fields(self) -> list[str]:
        missing = []

        for field in PROFILE_COMPLETION_FIELDS:
            value = getattr(self, field)

            if value is None:
                missing.append(field)
            elif isinstance(value, str) and not value.strip():
                missing.append(field)

        return missing

    def is_profile_complete(self) -> bool:
        return len(self.missing_completion_fields()) == 0

    # -----------------------------
    # DERIVED HEALTH PROPERTIES
    # -----------------------------
    @property
    def age(self) -> int | None:
        if not self.dob:
            return None
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    @property
    def bmi(self) -> float | None:
        if not self.current_weight_kg or not self.current_height_cm:
            return None
        height_m = self.current_height_cm / 100
        if height_m <= 0:
            return None
        return round(self.current_weight_kg / (height_m ** 2), 2)

    @property
    def bmi_category(self) -> str | None:
        bmi = self.bmi
        if bmi is None:
            return None
        if bmi < 18.5:
            return "Underweight"
        elif 18.5 <= bmi < 25:
            return "Normal"
        elif 25 <= bmi < 30:
            return "Overweight"
        else:
            return "Obese"
    
    @property
    def user_name(self):
        return self.user.full_name

    @property
    def user_email(self):
        return self.user.email

    def __str__(self):
        return f"Profile(user_id={self.user_id})"

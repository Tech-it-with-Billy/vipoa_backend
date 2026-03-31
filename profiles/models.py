import uuid
import secrets
from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from rewards.services.events import award_profile_completion
from rewards.services.wallet import get_or_create_wallet
from .constants import PROFILE_COMPLETION_FIELDS


def profile_avatar_upload_path(instance, filename: str) -> str:
    return f"profiles/{instance.user_id}/avatar/{filename}"


class SupabaseUserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        uid = extra_fields.get("id") or uuid.uuid4()
        email = self.normalize_email(email)
        user = self.model(id=uid, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email=email, password=password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email=email, password=password, **extra_fields)


class SupabaseUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = SupabaseUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
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
    day_streak = models.IntegerField(default=0)
    profile_completed_awarded = models.BooleanField(default=False)

    # -----------------------------
    # REFERRAL
    # -----------------------------
    referral_code = models.CharField(max_length=12, unique=True, blank=True)
    referred_by = models.CharField(max_length=12, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = secrets.token_hex(6).upper()
        super().save(*args, **kwargs)

    # -----------------------------
    # WALLET BALANCE
    # -----------------------------
    @property
    def poa_points(self):
        try:
            wallet = get_or_create_wallet(self.user)
            return wallet.balance if wallet else 0
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
        multiplier = activity_multipliers.get(
            self.activity_level.lower() if self.activity_level else "", 1.2
        )
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


class Referral(models.Model):
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_received"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["referrer", "referred_user"], name="uq_referral_referrer_referred"),
            models.UniqueConstraint(fields=["referred_user"], name="uq_referral_referred_once"),
            models.CheckConstraint(
                check=~models.Q(referrer=models.F("referred_user")),
                name="ck_referral_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["referrer", "created_at"]),
            models.Index(fields=["referred_user"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Referral(referrer={self.referrer.email}, referred={self.referred_user.email})"
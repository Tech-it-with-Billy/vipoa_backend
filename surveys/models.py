from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class SurveyDefinition(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("archived", "Archived"),
    ]

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    points_reward = models.PositiveIntegerField(default=30)

    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Optional survey thumbnail for listing UI."
    )

    ai_tags = models.JSONField(null=True, blank=True)
    ai_context = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_surveys"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class SurveyQuestion(models.Model):
    FIELD_TYPES = [
        ("single_choice", "Single choice"),
        ("multiple_choice", "Multiple choice"),
        ("short_text", "Short text"),
        ("long_text", "Long text"),
        ("number", "Number"),
        ("date", "Date"),
    ]

    survey = models.ForeignKey(
        SurveyDefinition,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    key = models.CharField(max_length=100)
    label = models.CharField(max_length=500)
    field_type = models.CharField(max_length=50, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)

    options = models.JSONField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        unique_together = ("survey", "key")

    def __str__(self):
        return f"{self.survey.slug} -> {self.key}"


class SurveyResponse(models.Model):
    survey = models.ForeignKey(
        SurveyDefinition,
        on_delete=models.CASCADE,
        related_name="responses"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="survey_responses"
    )

    answers = models.JSONField()
    metadata = models.JSONField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Response by {self.user} to {self.survey.slug}"

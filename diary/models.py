from django.db import models
from django.conf import settings

class DiaryEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="diary_entries")
    date = models.DateField()
    breakfast = models.CharField(max_length=255, blank=True)
    lunch = models.CharField(max_length=255, blank=True)
    dinner = models.CharField(max_length=255, blank=True)
    snack = models.CharField(max_length=255, blank=True)
    water_glasses = models.PositiveIntegerField(default=0)  # Number of glasses (max 8)
    points_earned = models.PositiveIntegerField(default=0)  # Computed points

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"DiaryEntry(user={self.user_id}, date={self.date})"

    def calculate_points(self):
        meal_points = 0
        for meal in [self.breakfast, self.lunch, self.dinner, self.snack]:
            if meal:
                meal_points += 2  # 2 points per meal
        water_points = min(self.water_glasses, 8)  # max 8 points
        self.points_earned = meal_points + water_points
        return self.points_earned
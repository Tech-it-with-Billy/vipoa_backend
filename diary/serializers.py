from rest_framework import serializers
from .models import DiaryEntry
from datetime import date

class DiaryEntrySerializer(serializers.ModelSerializer):
    date = serializers.DateField(default=date.today)
    points_earned = serializers.IntegerField(read_only=True)

    class Meta:
        model = DiaryEntry
        fields = ["id", "date", "breakfast", "lunch", "dinner", "snack", "water_glasses", "points_earned"]

class DiaryProgressSerializer(serializers.Serializer):
    total_points = serializers.IntegerField()
    entries_count = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
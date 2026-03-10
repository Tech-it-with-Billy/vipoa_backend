from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils.dateparse import parse_date
from django.db.models import Sum
from .services.rewards_integration import award_diary_points_to_wallet

from .models import DiaryEntry
from .serializers import DiaryEntrySerializer, DiaryProgressSerializer

class DiaryEntryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entries = DiaryEntry.objects.filter(user=request.user).order_by("-date")
        serializer = DiaryEntrySerializer(entries, many=True)
        return Response(serializer.data)

    def post(self, request):
        today_str = request.data.get("date") or str(date.today())
        entry, created = DiaryEntry.objects.get_or_create(user=request.user, date=today_str)
        serializer = DiaryEntrySerializer(entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        entry.calculate_points()
        entry.save(update_fields=["points_earned"])
        
        # Award points to Rewards wallet
        award_diary_points_to_wallet(request.user, entry)
        
        return Response(DiaryEntrySerializer(entry).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

class DiaryEntryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, date):
        entry = DiaryEntry.objects.filter(user=request.user, date=date).first()
        if not entry:
            return Response({"detail": "Diary entry not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = DiaryEntrySerializer(entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        entry.calculate_points()
        entry.save(update_fields=["points_earned"])
        
        # Update existing claim if exists
        award_diary_points_to_wallet(request.user, entry)
        
        return Response(DiaryEntrySerializer(entry).data)

class DiaryProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date = parse_date(request.query_params.get("start_date")) or None
        end_date = parse_date(request.query_params.get("end_date")) or None

        qs = DiaryEntry.objects.filter(user=request.user)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)

        total_points = qs.aggregate(total=Sum("points_earned"))["total"] or 0
        serializer = DiaryProgressSerializer({
            "total_points": total_points,
            "entries_count": qs.count(),
            "start_date": start_date or qs.earliest("date").date if qs.exists() else None,
            "end_date": end_date or qs.latest("date").date if qs.exists() else None,
        })
        return Response(serializer.data)
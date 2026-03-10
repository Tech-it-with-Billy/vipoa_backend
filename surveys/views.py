from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import SurveyDefinition
from .serializers import (
    SurveyDefinitionListSerializer,
    SurveyDefinitionDetailSerializer,
    SurveyResponseCreateSerializer,
)


class SurveyListView(generics.ListAPIView):
    """
    GET /api/surveys/
    Returns all ACTIVE surveys for the listing screen.
    """
    serializer_class = SurveyDefinitionListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SurveyDefinition.objects.filter(status="active")


class SurveyDetailView(generics.RetrieveAPIView):
    """
    GET /api/surveys/<slug>/
    Returns full survey details + questions.
    """
    serializer_class = SurveyDefinitionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return SurveyDefinition.objects.filter(status="active")


class SubmitSurveyView(APIView):
    """
    POST /api/surveys/<slug>/submit/
    Body:
    {
      "answers": { ... } 
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, slug):
        try:
            survey = SurveyDefinition.objects.get(slug=slug, status="active")
        except SurveyDefinition.DoesNotExist:
            return Response(
                {"detail": "Survey not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SurveyResponseCreateSerializer(
            data=request.data,
            context={"request": request, "survey": survey},
        )
        serializer.is_valid(raise_exception=True)

        response, points_awarded = serializer.save()

        return Response(
            {
                "detail": "Survey submitted successfully.",
                "survey": survey.slug,
                "points_awarded": points_awarded,
            },
            status=status.HTTP_201_CREATED,
        )

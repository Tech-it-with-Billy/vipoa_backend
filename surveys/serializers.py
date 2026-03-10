from rest_framework import serializers
from .models import SurveyDefinition, SurveyQuestion, SurveyResponse


class SurveyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyQuestion
        fields = ["key", "label", "field_type", "is_required", "options", "order"]


class SurveyDefinitionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyDefinition
        fields = ["slug", "name", "description", "points_reward"]


class SurveyDefinitionDetailSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = SurveyDefinition
        fields = [
            "slug",
            "name",
            "description",
            "points_reward",
            "questions",
        ]


class SurveyResponseCreateSerializer(serializers.Serializer):
    """
    Used by Submit endpoint. We don't expose model directly
    so we can validate against survey definition.
    """

    answers = serializers.JSONField()

    def validate(self, attrs):
        request = self.context["request"]
        survey = self.context["survey"]
        answers = attrs["answers"]

        # Basic validation: required fields present
        questions = survey.questions.all()
        missing_required = []
        for q in questions:
            if q.is_required and q.key not in answers:
                missing_required.append(q.key)

        if missing_required:
            raise serializers.ValidationError(
                {"missing_required": missing_required}
            )

        # You can add extra type validation here if needed

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        survey = self.context["survey"]
        user = request.user

        response = SurveyResponse.objects.create(
            survey=survey,
            user=user,
            answers=validated_data["answers"],
            metadata={
                "user_agent": request.META.get("HTTP_USER_AGENT"),
                "ip": request.META.get("REMOTE_ADDR"),
            },
        )

        # Award PoaPoints here (hook into your existing system)
        from .services import award_survey_points  # you'll create this

        points_awarded = award_survey_points(user=user, survey=survey)

        return response, points_awarded

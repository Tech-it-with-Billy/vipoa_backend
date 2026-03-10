from rest_framework import serializers



class RedemptionCreateSerializer(serializers.Serializer):
    reference_key = serializers.CharField(max_length=255)
    cost = serializers.IntegerField(min_value=1)
    provider = serializers.CharField(max_length=80, required=False, allow_blank=True)
    target = serializers.CharField(max_length=120, required=False, allow_blank=True)
    meta = serializers.JSONField(required=False)

    def validate_reference_key(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("reference_key is required.")
        return value


class RedemptionResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    reference_key = serializers.CharField()
    status = serializers.CharField()
    cost = serializers.IntegerField()
    provider = serializers.CharField(allow_blank=True)
    target = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    meta = serializers.JSONField()
    wallet = serializers.JSONField()

class RewardClaimListSerializer(serializers.Serializer):
    reference_key = serializers.CharField()
    event_type = serializers.CharField()
    event_id = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    applied_at = serializers.DateTimeField(allow_null=True)
    meta = serializers.JSONField()
from rest_framework import serializers
from .models import Product, Capture, Review


# ==========================================================
# PRODUCT SERIALIZER
# ==========================================================
class ProductSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "category", "image"]


# ==========================================================
# CAPTURE SERIALIZERS
# ==========================================================
class CaptureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capture
        fields = [
            "id",
            "image",
            "category",
            "size",
            "price",
            "location",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CaptureCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capture
        fields = ["image", "category", "size", "price", "location"]

    def validate_category(self, value: str):
        if not value:
            raise serializers.ValidationError("Category is required.")
        return value


# ==========================================================
# REVIEW SERIALIZER (read-only)
# ==========================================================
class ReviewSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "capture",
            "product",
            "custom_product_name",
            "review_text",
            "created_at",
        ]


# ==========================================================
# REVIEW SUBMIT SERIALIZER (write-only)
# Fixes 400 errors for CameraReview
# ==========================================================
class ReviewSubmitSerializer(serializers.Serializer):
    capture_id = serializers.IntegerField()

    # Optional fields (MUST accept blank + null)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    custom_product_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    review_text = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    def validate(self, attrs):
        # -----------------------------
        # 1. Ensure capture exists
        # -----------------------------
        try:
            attrs["capture"] = Capture.objects.get(id=attrs["capture_id"])
        except Capture.DoesNotExist:
            raise serializers.ValidationError({"capture_id": "Capture not found."})

        # -----------------------------
        # 2. If product_id provided → validate
        # -----------------------------
        product_id = attrs.get("product_id")
        if product_id:
            if not Product.objects.filter(id=product_id).exists():
                raise serializers.ValidationError({"product_id": "Product does not exist."})
            attrs["product"] = Product.objects.get(id=product_id)
        else:
            attrs["product"] = None

        # -----------------------------
        # 3. Fill product name if missing
        # -----------------------------
        if not attrs.get("custom_product_name"):
            # fallback: category → name (e.g. "flour" → "Flour")
            category_slug = attrs["capture"].category
            auto_name = category_slug.replace("_", " ").title()
            attrs["custom_product_name"] = auto_name

        # -----------------------------
        # 4. Auto-fill empty review_text
        # -----------------------------
        if not attrs.get("review_text"):
            attrs["review_text"] = "Product review submitted"

        return attrs

    # -----------------------------
    # 5. Create Review instance
    # -----------------------------
    def create(self, validated_data):
        return Review.objects.create(
            capture=validated_data["capture"],
            product=validated_data.get("product"),
            custom_product_name=validated_data.get("custom_product_name"),
            review_text=validated_data.get("review_text", ""),
            user=self.context["request"].user,
        )

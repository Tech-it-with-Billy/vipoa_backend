from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product, Capture, Review
from .serializers import (
    ProductSerializer,
    CaptureSerializer,
    CaptureCreateSerializer,
    ReviewSerializer,
    ReviewSubmitSerializer,
)


# ==========================================================
# PRODUCT LIST ENDPOINT (unchanged)
# ==========================================================
class ProductListView(generics.ListAPIView):
    """
    GET /api/reviews/products/?category=flour|sugar|oil|...
    Used by ProductListingScreen.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.objects.all()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs


# ==========================================================
# CAPTURE CREATE (Camera Upload)
# ==========================================================
class CaptureCreateView(APIView):
    """
    POST /api/reviews/capture/
    Multipart:
      image, category, size, price, location
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = CaptureCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        capture = serializer.save(user=request.user)

        return Response(
            {
                "capture_id": capture.id,
                "capture": CaptureSerializer(capture).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ==========================================================
# REVIEW SUBMIT (Final, Cleaned, Serializer-Controlled)
# ==========================================================
class ReviewSubmitView(APIView):
    """
    POST /api/reviews/submit/
    JSON Body:
      {
        "capture_id": 123,
        "review_text": "optional",
        "product_id": 1,                # optional
        "custom_product_name": "XYZ"    # optional
      }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ReviewSubmitSerializer(
            data=request.data,
            context={"request": request}
        )

        # 1) Serializer validation handles everything now
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 2) Serializer.create() handles:
        #    - capture lookup
        #    - optional product_id
        #    - optional custom name
        #    - fallback name
        #    - fallback review text
        #    - saving review instance
        review = serializer.save()

        return Response(
            {"review": ReviewSerializer(review).data},
            status=status.HTTP_201_CREATED,
        )

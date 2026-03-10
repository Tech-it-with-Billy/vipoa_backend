from django.urls import path
from .views import CaptureCreateView, ReviewSubmitView, ProductListView

urlpatterns = [
    path("capture/", CaptureCreateView.as_view(), name="reviews-capture"),
    path("submit/", ReviewSubmitView.as_view(), name="reviews-submit"),
    path("products/", ProductListView.as_view(), name="reviews-product-list"),
]

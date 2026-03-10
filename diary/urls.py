from django.urls import path
from .views import DiaryEntryListView, DiaryEntryDetailView, DiaryProgressView

urlpatterns = [
    path("entries/", DiaryEntryListView.as_view(), name="diary-entries"),
    path("entries/<str:date>/", DiaryEntryDetailView.as_view(), name="diary-entry-detail"),
    path("progress/", DiaryProgressView.as_view(), name="diary-progress"),
]
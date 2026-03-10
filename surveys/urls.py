from django.urls import path
from .views import SurveyListView, SurveyDetailView, SubmitSurveyView

app_name = "surveys"

urlpatterns = [
    path("", SurveyListView.as_view(), name="survey-list"),
    path("<slug:slug>/", SurveyDetailView.as_view(), name="survey-detail"),
    path("<slug:slug>/submit/", SubmitSurveyView.as_view(), name="survey-submit"),
]

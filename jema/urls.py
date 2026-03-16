from django.urls import path
from . import views

app_name = 'jema'

urlpatterns = [
    path('chat/', views.chat, name='chat'),
    path('recipes/', views.recipes, name='recipes'),
    path('suggest/', views.suggest, name='suggest'),
    path('sessions/', views.sessions, name='sessions_list'),
    path('sessions/<int:session_id>/', views.sessions, name='session_detail'),
    path('health/', views.health, name='health'),
]

"""
Jema URL Configuration
API endpoints for the Jema cooking assistant.
"""

from django.urls import path
from . import views

app_name = 'jema'

urlpatterns = [
    # Chat endpoint
    path('chat/', views.chat, name='chat'),
    
    # Recipes endpoints
    path('recipes/', views.recipes, name='recipes'),
    
    # Query endpoint (recipe + nutrition route)
    path('query/', views.query, name='query'),
    # Recipe and nutrition dedicated endpoints
    path('recipe/', views.query, name='recipe'),
    path('nutrition/', views.query, name='nutrition'),
    path('integrated/', views.integrated, name='integrated'),
    
    # Suggestions endpoint
    path('suggest/', views.suggest, name='suggest'),
    
    # Session management
    path('sessions/', views.sessions, name='sessions_list'),
    path('sessions/<int:session_id>/', views.sessions, name='session_detail'),
    
    # Health check
    path('health/', views.health, name='health'),
]

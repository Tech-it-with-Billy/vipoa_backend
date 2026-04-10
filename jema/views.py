"""
Jema Django Views
HTTP API endpoints for the Jema cooking assistant.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jema.models import ChatSession, ChatMessage
from jema.serializers import ChatSessionSerializer, ChatMessageSerializer
from jema.services.jema_engine import JemaEngine
from jema.services.jema_modelling import (
    run_jema_model,
    answer_with_rag,
    answer_with_integrated_pipeline,
    recipes_features_df,
)

logger = logging.getLogger(__name__)

# Global engine instance (initialized on first use)
_engine = None
# Session-specific engines cache
_session_engines = {}


def _df_to_records(df):
    return json.loads(df.to_json(orient="records"))


def _is_nutrition_query(text: str) -> bool:
    text_lower = text.lower()
    recipe_starters = [
        'i have', 'we have', 'i got', 'i have ingredients',
        'with these', 'using', 'what can i make with'
    ]
    health_keywords = [
        'nutrition', 'diet', 'health', 'diabetes', 'hypertension',
        'inflammatory', 'calories', 'allergy', 'intolerance', 'pregnant',
        'weight loss', 'cholesterol', 'kidney', 'heart'
    ]
    if any(starter in text_lower for starter in recipe_starters) and any(k in text_lower for k in ['ingredients', 'cook', 'recipe', 'make']):
        return False
    if any(h in text_lower for h in health_keywords) and any(q in text_lower for q in ['is', 'should', 'can i', 'good for', 'bad for']):
        return True
    recipe_score = sum(1 for kw in ['have', 'cook', 'make', 'recipe', 'ingredients', 'minutes'] if kw in text_lower)
    health_score = sum(1 for kw in health_keywords if kw in text_lower)
    if health_score > recipe_score:
        return True
    return False


def get_engine():
    """Lazy-load the Jema engine."""
    global _engine
    if _engine is None:
        try:
            _engine = JemaEngine()
        except Exception as e:
            logger.error(f"Failed to initialize JemaEngine: {e}")
            raise
    return _engine

def get_session_engine(session_id: int, user=None):
    if session_id not in _session_engines:
        try:
            _session_engines[session_id] = JemaEngine(user=user)
        except Exception as e:
            logger.error(f"Failed to initialize session engine {session_id}: {e}")
            raise
    return _session_engines[session_id]


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def chat(request):
    try:
        # Parse request
        if isinstance(request.data, dict):
            data = request.data
        else:
            data = json.loads(request.body)
        
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        user_id = data.get('user_id')
        
        if not user_message:
            return Response(
                {"error": "Message field is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Fetch user for personalization (optional)
        user = None
        if user_id:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=user_id)
            except Exception as e:
                logger.debug(f"Could not fetch user {user_id}: {e}")
                user = None
        
        # Fetch user profile context for personalization
        user_profile = None
        try:
            if user and user.is_authenticated:
                from profiles.services import get_user_profile_context
                user_profile = get_user_profile_context(user)
        except Exception as e:
            logger.error(f"Profile fetch failed for user {getattr(user, 'id', 'unknown')}: {e}")
            user_profile = None
        
        # Get session-specific engine for state isolation
        if session_id:
            try:
                session_id_int = int(session_id)
                engine = get_session_engine(session_id_int, user=user)
            except (ValueError, TypeError):
                # Invalid session_id, use global engine
                engine = get_engine()
        else:
            # No session, use global engine
            engine = get_engine()
        
        # Process message with user profile
        response = engine.process_message(
            user_input=user_message,
            user_profile=user_profile,
        )
        
        # Optionally persist to database
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id)
                ChatMessage.objects.create(
                    session=session,
                    role='user',
                    content=user_message
                )
                ChatMessage.objects.create(
                    session=session,
                    role='assistant',
                    content=response.get('message', '')
                )
            except ChatSession.DoesNotExist:
                logger.warning(f"ChatSession {session_id} not found")
        
        return Response(response, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"ChatView unhandled error: {e}")
        return JsonResponse(
            {"response": "I'm having trouble right now. Please try again in a moment."},
            status=200
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def query(request):
    """
    POST /api/jema/query/

    Classify and route to recipe recommendation or nutrition RAG.
    Request:
      { "text": "I have tomatoes and eggs" }
    Response:
      {
        "pipeline": "recipe_recommender" or "nutrition_rag",
        "data": {...}
      }
    """
    try:
        data = request.data if isinstance(request.data, dict) else json.loads(request.body)
        text = data.get('text', '').strip()
        if not text:
            return Response({"error": "text field is required"}, status=status.HTTP_400_BAD_REQUEST)

        if _is_nutrition_query(text):
            result = answer_with_rag(text, language='en')
            return Response({"pipeline": "nutrition_rag", "data": result}, status=status.HTTP_200_OK)

        recipe_result = run_jema_model(text, recipes_features_df, top_k=5)
        return Response({"pipeline": "recipe_recommender", "data": recipe_result}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in query endpoint: {e}", exc_info=True)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def integrated(request):
    """POST /api/jema/integrated/ - integrated recipe + nutrition explanation"""
    try:
        data = request.data if isinstance(request.data, dict) else json.loads(request.body)
        text = data.get('text', '').strip()
        if not text:
            return Response({"error": "text field is required"}, status=status.HTTP_400_BAD_REQUEST)

        persona = data.get('persona')
        language = data.get('language')

        result = answer_with_integrated_pipeline(
            user_query=text,
            language=language,
            persona=persona,
            top_recipes=3,
            top_contexts=3,
            debug=False,
        )
        return Response({"pipeline": "integrated", "data": result}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in integrated endpoint: {e}", exc_info=True)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@csrf_exempt
def recipes(request):
    """
    GET /api/jema/recipes/
    Retrieve all available recipes (paginated).
    
    POST /api/jema/recipes/search/
    Search recipes by name, country, or ingredients.
    
    Query params:
    - page: int (default 1)
    - limit: int (default 10)
    - search: str (recipe name or country)
    """
    try:
        engine = get_engine()
        
        if request.method == 'GET':
            # Paginate recipes
            page = int(request.GET.get('page', 1))
            limit = int(request.GET.get('limit', 10))
            search = request.GET.get('search', '').lower()
            
            recipes_df = engine.recipes_df
            
            if search:
                recipes_df = recipes_df[
                    recipes_df['meal_name'].str.lower().str.contains(search, na=False) |
                    recipes_df['country'].str.lower().str.contains(search, na=False)
                ]
            
            # Pagination
            total = len(recipes_df)
            start = (page - 1) * limit
            end = start + limit
            
            paginated = recipes_df.iloc[start:end]
            recipes_list = _df_to_records(paginated)
            
            return Response({
                "recipes": recipes_list,
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }, status=status.HTTP_200_OK)
        
        else:
            # POST - search
            data = request.data if isinstance(request.data, dict) else json.loads(request.body)
            search = data.get('search', '').lower()
            
            if not search:
                return Response(
                    {"error": "Search field is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            recipes_df = engine.recipes_df
            results = recipes_df[
                recipes_df['meal_name'].str.lower().str.contains(search, na=False) |
                recipes_df['country'].str.lower().str.contains(search, na=False)
            ]
            
            return Response({
                "results": _df_to_records(results),
                "count": len(results)
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error in recipes endpoint: {e}", exc_info=True)
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def suggest(request):
    """
    POST /api/jema/suggest/
    
    Get recipe suggestions based on ingredients.
    
    Request body:
    {
        "ingredients": ["rice", "beans", "tomato"],
        "constraints": ["quick", "vegetarian"]
    }
    
    Response:
    {
        "suggestions": [
            {
                "meal_name": "Rice and Beans",
                "country": "Kenya",
                "match_percentage": 0.95,
                "missing_ingredients": ["oil"]
            },
            ...
        ]
    }
    """
    try:
        data = request.data if isinstance(request.data, dict) else json.loads(request.body)
        
        ingredients = data.get('ingredients', [])
        constraints = data.get('constraints', [])
        
        if not ingredients:
            return Response(
                {"error": "Ingredients field is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        engine = get_engine()
        
        # Use ingredient normalizer to normalize inputs
        from jema.src.ingredient_normalizer_v2 import IngredientNormalizer
        normalized = IngredientNormalizer.normalize_list(ingredients)
        
        # Build constraints dict
        user_constraints = {}
        if "quick" in [c.lower() for c in constraints]:
            user_constraints['quick'] = True
        
        # Match recipes
        matches = engine.matcher.match(
            user_ingredients=normalized,
            user_constraints=user_constraints,
            min_match_percentage=0.3
        )
        
        # Format suggestions
        suggestions = []
        for match in matches[:10]:  # Top 10
            recipe = engine.recipes_df[engine.recipes_df['meal_name'] == match.name]
            if not recipe.empty:
                recipe_data = recipe.iloc[0].to_dict()
                suggestions.append({
                    "meal_name": match.name,
                    "country": recipe_data.get('country', ''),
                    "cook_time": recipe_data.get('cook_time', ''),
                    "match_percentage": round(match.match_percentage, 2),
                    "missing_ingredients": match.missing_ingredients[:3]
                })
        
        return Response({
            "suggestions": suggestions,
            "count": len(suggestions)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Error in suggest endpoint: {e}", exc_info=True)
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([AllowAny])
@csrf_exempt
def sessions(request, session_id=None):
    """
    GET /api/jema/sessions/
    List all chat sessions.
    
    GET /api/jema/sessions/{id}/
    Get a specific chat session with all messages.
    
    POST /api/jema/sessions/
    Create a new chat session.
    
    DELETE /api/jema/sessions/{id}/
    Delete a chat session.
    """
    try:
        if request.method == 'GET':
            if session_id:
                # Get single session
                session = ChatSession.objects.get(id=session_id)
                serializer = ChatSessionSerializer(session)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                # List all sessions
                sessions = ChatSession.objects.all().prefetch_related('messages').order_by('-session_started')
                serializer = ChatSessionSerializer(sessions, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)
        
        elif request.method == 'POST':
            # Create new session
            data = request.data if isinstance(request.data, dict) else json.loads(request.body)
            user_id = data.get('user_id')
            
            session = ChatSession.objects.create(user_id=user_id)
            serializer = ChatSessionSerializer(session)
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        elif request.method == 'DELETE':
            if not session_id:
                return Response(
                    {"error": "session_id is required for DELETE"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            session = ChatSession.objects.get(id=session_id)
            session.delete()
            
            return Response(
                {"message": f"Session {session_id} deleted"},
                status=status.HTTP_204_NO_CONTENT
            )
    
    except ChatSession.DoesNotExist:
        return Response(
            {"error": f"Session {session_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error in sessions endpoint: {e}", exc_info=True)
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """
    GET /api/jema/health/
    Health check endpoint.
    """
    try:
        engine = get_engine()
        recipe_count = len(engine.recipes_df) if engine.recipes_df is not None else 0
        
        return Response({
            "status": "ok",
            "recipes_loaded": recipe_count,
            "engine": "ready"
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({
            "status": "error",
            "message": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatMessageSerializer
from .services.jema_engine import JemaEngine

logger = logging.getLogger(__name__)

_engine = None
_session_engines = {}


def _df_to_records(df):
    return json.loads(df.to_json(orient='records'))


def get_engine():
    global _engine
    if _engine is None:
        _engine = JemaEngine()
    return _engine


def get_session_engine(session_id: int):
    if session_id not in _session_engines:
        _session_engines[session_id] = JemaEngine()
    return _session_engines[session_id]


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def chat(request):
    try:
        data = request.data if isinstance(request.data, dict) else json.loads(request.body)
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        user_id = data.get('user_id')

        if not user_message:
            return Response({'error': 'Message field is required'}, status=status.HTTP_400_BAD_REQUEST)

        if session_id:
            try:
                session_id_int = int(session_id)
                engine = get_session_engine(session_id_int)
            except (ValueError, TypeError):
                engine = get_engine()
        else:
            engine = get_engine()

        response = engine.process_message(user_message)

        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id)
                ChatMessage.objects.create(session=session, role='user', content=user_message)
                ChatMessage.objects.create(session=session, role='assistant', content=response.get('message', ''))
            except ChatSession.DoesNotExist:
                logger.warning(f"ChatSession {session_id} not found")

        return Response(response, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@csrf_exempt
def recipes(request):
    try:
        engine = get_engine()
        if request.method == 'GET':
            page = int(request.GET.get('page', 1))
            limit = int(request.GET.get('limit', 10))
            search = request.GET.get('search', '').lower()
            recipes_df = engine.recipes_df
            if search:
                recipes_df = recipes_df[
                    recipes_df['meal_name'].str.lower().str.contains(search, na=False) |
                    recipes_df['country'].str.lower().str.contains(search, na=False)
                ]
            total = len(recipes_df)
            start = (page - 1) * limit
            end = start + limit
            paginated = recipes_df.iloc[start:end]
            recipes_list = _df_to_records(paginated)
            return Response({'recipes': recipes_list, 'page': page, 'limit': limit, 'total': total, 'pages': (total + limit - 1) // limit}, status=status.HTTP_200_OK)
        else:
            data = request.data if isinstance(request.data, dict) else json.loads(request.body)
            search = data.get('search', '').lower()
            if not search:
                return Response({'error': 'Search field is required'}, status=status.HTTP_400_BAD_REQUEST)
            recipes_df = engine.recipes_df
            results = recipes_df[
                recipes_df['meal_name'].str.lower().str.contains(search, na=False) |
                recipes_df['country'].str.lower().str.contains(search, na=False)
            ]
            return Response({'results': _df_to_records(results), 'count': len(results)}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in recipes endpoint: {e}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def suggest(request):
    try:
        data = request.data if isinstance(request.data, dict) else json.loads(request.body)
        ingredients = data.get('ingredients', [])
        constraints = data.get('constraints', [])
        if not ingredients:
            return Response({'error': 'Ingredients field is required'}, status=status.HTTP_400_BAD_REQUEST)
        engine = get_engine()
        from .src.ingredient_normalizer_v2 import IngredientNormalizer
        normalized = IngredientNormalizer.normalize_list(ingredients)
        user_constraints = {}
        if 'quick' in [c.lower() for c in constraints]:
            user_constraints['quick'] = True
        matches = engine.matcher.match(user_ingredients=normalized, user_constraints=user_constraints, min_match_percentage=0.3)
        suggestions = []
        for match in matches[:10]:
            recipe = engine.recipes_df[engine.recipes_df['meal_name'] == match.name]
            if not recipe.empty:
                recipe_data = recipe.iloc[0].to_dict()
                suggestions.append({'meal_name': match.name, 'country': recipe_data.get('country', ''), 'cook_time': recipe_data.get('cook_time', ''), 'match_percentage': round(match.match_percentage, 2), 'missing_ingredients': match.missing_ingredients[:3]})
        return Response({'suggestions': suggestions, 'count': len(suggestions)}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in suggest endpoint: {e}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([AllowAny])
@csrf_exempt
def sessions(request, session_id=None):
    try:
        if request.method == 'GET':
            if session_id:
                session = ChatSession.objects.get(id=session_id)
                serializer = ChatSessionSerializer(session)
                return Response(serializer.data, status=status.HTTP_200_OK)
            sessions = ChatSession.objects.all().prefetch_related('messages').order_by('-session_started')
            serializer = ChatSessionSerializer(sessions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        elif request.method == 'POST':
            data = request.data if isinstance(request.data, dict) else json.loads(request.body)
            user_id = data.get('user_id')
            session = ChatSession.objects.create(user_id=user_id)
            serializer = ChatSessionSerializer(session)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        elif request.method == 'DELETE':
            if not session_id:
                return Response({'error': 'session_id is required for DELETE'}, status=status.HTTP_400_BAD_REQUEST)
            session = ChatSession.objects.get(id=session_id)
            session.delete()
            return Response({'message': f'Session {session_id} deleted'}, status=status.HTTP_204_NO_CONTENT)
    except ChatSession.DoesNotExist:
        return Response({'error': f'Session {session_id} not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error in sessions endpoint: {e}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    try:
        engine = get_engine()
        recipe_count = len(engine.recipes_df) if engine.recipes_df is not None else 0
        return Response({'status': 'healthy', 'recipes_loaded': recipe_count, 'engine': 'ready'}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

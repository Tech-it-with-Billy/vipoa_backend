"""
Integration Tests for Jema
Tests the end-to-end flow from views → engine → services → LLM
"""

import os
import sys
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vipoa_backend.settings')

import django
django.setup()

from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from rest_framework.test import APIClient

# Import Jema components
from jema.models import ChatSession
from jema.services.jema_engine import JemaEngine


def test_engine_initialization():
    """Test that JemaEngine initializes correctly."""
    print("\n[TEST 1] Engine Initialization...")
    try:
        engine = JemaEngine()
        print(f"✓ Engine initialized successfully")
        print(f"  - Recipes loaded: {len(engine.recipes_df)} recipes")
        print(f"  - Language: {engine.llm.current_language}")
        return True
    except Exception as e:
        print(f"✗ Engine initialization failed: {e}")
        return False


def test_greeting():
    """Test greeting intent."""
    print("\n[TEST 2] Greeting Intent...")
    try:
        engine = JemaEngine()
        response = engine.process_message("Hello, how are you?")
        
        print(f"✓ Greeting processed")
        print(f"  - Message: {response['message'][:100]}...")
        print(f"  - Language: {response['language']}")
        return True
    except Exception as e:
        print(f"✗ Greeting test failed: {e}")
        return False


def test_ingredient_matching():
    """Test ingredient-based recipe matching."""
    print("\n[TEST 3] Ingredient Matching...")
    try:
        engine = JemaEngine()
        response = engine.process_message("I have rice and beans")
        
        print(f"✓ Ingredient matching processed")
        print(f"  - Message: {response['message'][:100]}...")
        print(f"  - Recipes in response: {len(response['recipes'])}")
        return True
    except Exception as e:
        print(f"✗ Ingredient matching test failed: {e}")
        return False


def test_recipe_request():
    """Test specific recipe request."""
    print("\n[TEST 4] Recipe Request...")
    try:
        engine = JemaEngine()
        response = engine.process_message("Can you give me a recipe for ugali?")
        
        print(f"✓ Recipe request processed")
        print(f"  - Message: {response['message'][:100]}...")
        print(f"  - Recipe confirmed: {response['state']['recipe_confirmed']}")
        return True
    except Exception as e:
        print(f"✗ Recipe request test failed: {e}")
        return False


def test_conversation_flow():
    """Test a multi-turn conversation."""
    print("\n[TEST 5] Conversation Flow...")
    try:
        engine = JemaEngine()
        
        # Turn 1: Greeting
        response1 = engine.process_message("Hi Jema!")
        print(f"✓ Turn 1 (Greeting): {response1['message'][:50]}...")
        
        # Turn 2: Ingredients
        response2 = engine.process_message("I have maize and tomatoes")
        print(f"✓ Turn 2 (Ingredients): Got {len(response2['recipes'])} recipe suggestions")
        
        # Turn 3: Recipe selection (if available)
        if response2['recipes']:
            response3 = engine.process_message("1")
            print(f"✓ Turn 3 (Selection): Recipe confirmed: {response3['state']['recipe_confirmed']}")
        
        return True
    except Exception as e:
        print(f"✗ Conversation flow test failed: {e}")
        return False


def test_api_endpoints():
    """Test Django API endpoints."""
    print("\n[TEST 6] API Endpoints...")
    try:
        client = APIClient()
        
        # Test health check
        print("  Testing /api/jema/health/...")
        response = client.get('/api/jema/health/')
        print(f"✓ Health check: {response.status_code}")
        
        # Test chat endpoint
        print("  Testing /api/jema/chat/...")
        response = client.post('/api/jema/chat/', {
            'message': 'Hello Jema!'
        }, format='json')
        print(f"✓ Chat endpoint: {response.status_code}")
        data = response.json()
        print(f"  - Response has message: {'message' in data}")
        print(f"  - Response has state: {'state' in data}")
        
        # Test recipes endpoint
        print("  Testing /api/jema/recipes/...")
        response = client.get('/api/jema/recipes/')
        print(f"✓ Recipes endpoint: {response.status_code}")
        data = response.json()
        print(f"  - Total recipes: {data.get('total', 0)}")
        
        # Test suggestions endpoint
        print("  Testing /api/jema/suggest/...")
        response = client.post('/api/jema/suggest/', {
            'ingredients': ['rice', 'beans']
        }, format='json')
        print(f"✓ Suggest endpoint: {response.status_code}")
        data = response.json()
        print(f"  - Suggestions count: {data.get('count', 0)}")
        
        return True
    except Exception as e:
        print(f"✗ API endpoint tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("JEMA INTEGRATION TESTS")
    print("=" * 60)
    
    tests = [
        test_engine_initialization,
        test_greeting,
        test_ingredient_matching,
        test_recipe_request,
        test_conversation_flow,
        test_api_endpoints,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    return all(results)


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

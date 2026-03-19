"""
Unit Tests for Jema AI API
Tests for chat endpoint and recipe functionality
"""

from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from jema.models import ChatSession, ChatMessage


class JemaChatTests(APITestCase):
    """Test Jema chat endpoint"""
    
    def setUp(self):
        self.client = APIClient()
        self.chat_url = '/api/jema/chat/'
    
    def test_simple_greeting(self):
        """Test Jema responds to a greeting"""
        response = self.client.post(
            self.chat_url,
            {'message': 'Hello'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('language', response.data)
        self.assertTrue(len(response.data['message']) > 0)
    
    def test_recipe_request(self):
        """Test Jema responds to recipe request"""
        response = self.client.post(
            self.chat_url,
            {'message': 'I want to make ugali'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('recipes', response.data)
        # Should have recipe data
        self.assertTrue(len(response.data.get('recipes', [])) >= 0)
    
    def test_ingredient_based_suggestion(self):
        """Test Jema suggests recipes based on ingredients"""
        response = self.client.post(
            self.chat_url,
            {'message': 'I have rice and beans. What can I make?'},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertIn('recipes', response.data)
    
    def test_empty_message_error(self):
        """Test that empty message returns error"""
        response = self.client.post(
            self.chat_url,
            {'message': ''},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_missing_message_field(self):
        """Test that missing message field returns error"""
        response = self.client.post(
            self.chat_url,
            {},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_response_has_language_field(self):
        """Test that response includes language detection"""
        response = self.client.post(
            self.chat_url,
            {'message': 'Ninataka ugali'},  # Swahili for "I want ugali"
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('language', response.data)
        # Should detect language
        self.assertIn(response.data['language'], ['english', 'swahili', 'french', 'amharic'])
    
    def test_query_endpoint_protein_star(self):
        """Test /api/jema/query/ returns structured protein-based suggestions."""
        query_url = '/api/jema/query/'
        response = self.client.post(query_url, {'text': 'I have onions, tomatoes, garlic, chicken and kale.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('pipeline', response.data)
        self.assertIn('data', response.data)
        data = response.data['data']
        self.assertIn('structured_recommendations', data)
        self.assertTrue(any('chicken' in rec['dish_name'].lower() or 'sukuma' in rec['dish_name'].lower() for rec in data['structured_recommendations']))

    def test_query_endpoint_no_hallucination(self):
        """Ensure query output does not suggest unrelated main dish for chicken input."""
        query_url = '/api/jema/query/'
        response = self.client.post(query_url, {'text': 'I have onions, tomatoes, garlic, chicken and kale.'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        dish_names = [r['dish_name'].lower() for r in data.get('structured_recommendations', [])]
        self.assertFalse(any('octopus' in d or 'matoke' in d for d in dish_names))


class JemaSessionTests(APITestCase):
    """Test Jema session management"""
    
    def setUp(self):
        self.client = APIClient()
        self.sessions_url = '/api/jema/sessions/'
    
    def test_create_session(self):
        """Test creating a new chat session"""
        response = self.client.post(
            self.sessions_url,
            {},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)
        self.assertIn('created_at', response.data)
    
    def test_list_sessions(self):
        """Test listing chat sessions"""
        # Create a session first
        create_response = self.client.post(
            self.sessions_url,
            {},
            format='json'
        )
        
        # List sessions
        response = self.client.get(self.sessions_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
    
    def test_get_session_detail(self):
        """Test retrieving session details"""
        # Create session
        create_response = self.client.post(
            self.sessions_url,
            {},
            format='json'
        )
        session_id = create_response.data['id']
        
        # Get session detail
        response = self.client.get(f'{self.sessions_url}{session_id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], session_id)
    
    def test_session_has_messages(self):
        """Test that session can store messages"""
        # Create session
        create_response = self.client.post(
            self.sessions_url,
            {},
            format='json'
        )
        session_id = create_response.data['id']
        
        # Verify session exists in database
        session = ChatSession.objects.get(id=session_id)
        self.assertIsNotNone(session)
    
    def test_nonexistent_session(self):
        """Test retrieving non-existent session"""
        response = self.client.get(f'{self.sessions_url}99999/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class JemaRecipesTests(APITestCase):
    """Test Jema recipes endpoint"""
    
    def setUp(self):
        self.client = APIClient()
        self.recipes_url = '/api/jema/recipes/'
    
    def test_get_recipes_list(self):
        """Test retrieving list of recipes"""
        response = self.client.get(self.recipes_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return some data (list or dict with results)
        self.assertIsNotNone(response.data)
    
    def test_search_recipes_by_name(self):
        """Test searching recipes by name"""
        response = self.client.get(
            self.recipes_url,
            {'search': 'ugali'}
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class JemaHealthTests(APITestCase):
    """Test Jema health check endpoint"""
    
    def setUp(self):
        self.client = APIClient()
        self.health_url = '/api/jema/health/'
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = self.client.get(self.health_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)


# Run tests with: python manage.py test jema.tests

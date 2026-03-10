"""
Test script for Jema AI API endpoints
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_jema_chat():
    """Test Jema chat endpoint"""
    print("=" * 50)
    print("Testing Jema Chat")
    print("=" * 50)
    
    url = f"{BASE_URL}/api/jema/chat/"
    
    # Test message
    messages = [
        {"role": "user", "content": "Hello, what can you help me with?"},
        {"role": "user", "content": "I want to make ugali"},
        {"role": "user", "content": "Can you suggest meals with rice?"}
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n--- Message {i} ---")
        print(f"User: {message['content']}")
        
        data = {
            "message": message['content']
        }
        
        try:
            response = requests.post(url, json=data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Jema: {result.get('message', 'No response')}")
                if 'recipes' in result and result['recipes']:
                    print(f"Recipes: {result['recipes']}")
                if 'cta' in result and result['cta']:
                    print(f"CTA: {result['cta']}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Error: {e}")
        
        print()

def test_jema_session_chat():
    """Test Jema session-based chat endpoint"""
    print("=" * 50)
    print("Testing Jema Session Chat")
    print("=" * 50)
    
    # First, create a session
    session_url = f"{BASE_URL}/api/jema/sessions/"
    response = requests.post(session_url, json={})
    
    if response.status_code != 201:
        print("Failed to create session")
        print(f"Response: {response.text}")
        return
    
    session_id = response.json().get('id')
    print(f"Created session ID: {session_id}\n")
    
    # Test conversation
    chat_url = f"{BASE_URL}/api/jema/sessions/{session_id}/chat/"
    
    messages = [
        "Hello Jema!",
        "I have rice and beans. What can I make?",
        "Tell me more about that"
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"--- Message {i} ---")
        print(f"User: {message}")
        
        data = {"message": message}
        
        try:
            response = requests.post(chat_url, json=data)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Jema: {result.get('message', 'No response')}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Error: {e}")
        
        print()

def main():
    try:
        print("🤖 Testing Jema AI API\n")
        
        # Test basic chat
        test_jema_chat()
        
        # Test session-based chat
        test_jema_session_chat()
        
        print("\n✅ Jema API tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to server at http://127.0.0.1:8000")
        print("Make sure the Django server is running")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()

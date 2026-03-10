"""
Simple Jema API Test - Focus on chat functionality
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

print("🤖 Testing Jema AI Chat\n")
print("=" * 60)

# Test messages
messages = [
    "Hello, what can you help me with?",
    "I want to make ugali",
    "I have rice and beans. What can I make?",
    "Tell me about pilau"
]

for i, user_message in enumerate(messages, 1):
    print(f"\n{i}. User: {user_message}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/jema/chat/",
            json={"message": user_message}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Jema: {data.get('message', 'No response')}")
            print(f"   Language: {data.get('language', 'N/A')}")
            
            if data.get('recipes'):
                print(f"   Recipes: {len(data['recipes'])} found")
                
        else:
            print(f"   Error: Status {response.status_code}")
            
    except Exception as e:
        print(f"   Error: {e}")

print("\n" + "=" * 60)
print("✅ Test completed!")

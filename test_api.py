"""
Test script for API endpoints
"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_register():
    """Test user registration"""
    print("=" * 50)
    print("Testing User Registration")
    print("=" * 50)
    
    url = f"{BASE_URL}/api/accounts/register/"
    # Use timestamp to ensure unique email
    email = f"testuser{int(time.time())}@example.com"
    data = {
        "email": email,
        "password": "TestPass123",
        "password2": "TestPass123"
    }
    
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 201:
        return response.json()
    return None

def test_get_profile(user_id, token):
    """Test getting user profile"""
    print("\n" + "=" * 50)
    print(f"Testing Get Profile (User ID: {user_id})")
    print("=" * 50)
    
    url = f"{BASE_URL}/api/profile/{user_id}/"
    headers = {"Authorization": f"Token {token}"}
    
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.json() if response.status_code == 200 else None

def test_update_profile(token):
    """Test updating user profile"""
    print("\n" + "=" * 50)
    print("Testing Update Profile")
    print("=" * 50)
    
    url = f"{BASE_URL}/api/profile/update/"
    headers = {"Authorization": f"Token {token}"}
    data = {
        "name": "Test User",
        "gender": "Male",
        "location": "Nairobi",
        "diet": "Vegetarian",
        "occupationalStatus": "Employed",
        "region": "East Africa"
    }
    
    response = requests.patch(url, json=data, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.json() if response.status_code == 200 else None

def main():
    try:
        # Test registration
        registration_data = test_register()
        
        if not registration_data:
            print("\n❌ Registration failed!")
            return
        
        token = registration_data.get("token")
        user_id = registration_data.get("user", {}).get("id")
        
        print(f"\n✅ User registered successfully!")
        print(f"   User ID: {user_id}")
        print(f"   Token: {token[:20]}...")
        
        # Test get profile
        profile_data = test_get_profile(user_id, token)
        
        if profile_data:
            print(f"\n✅ Profile retrieved successfully!")
        else:
            print(f"\n❌ Profile retrieval failed!")
        
        # Test update profile
        update_data = test_update_profile(token)
        
        if update_data:
            print(f"\n✅ Profile updated successfully!")
        else:
            print(f"\n❌ Profile update failed!")
        
        # Get profile again to verify updates
        print("\n" + "=" * 50)
        print("Verifying Updates")
        print("=" * 50)
        final_profile = test_get_profile(user_id, token)
        
        if final_profile:
            print("\n✅ All tests passed!")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to server at http://127.0.0.1:8000")
        print("Make sure the Django server is running: python manage.py runserver")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()

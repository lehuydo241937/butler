import requests
import json
import base64
import os

# Configuration
BASE_URL = "http://localhost:8000"

def test_health():
    """Tests the /health endpoint."""
    print("\n--- Testing Health Check ---")
    try:
        response = requests.get(f"{BASE_URL}/health")
        response.raise_for_status()
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Health check failed: {e}")

def test_list_sessions():
    """Tests the /sessions endpoint."""
    print("\n--- Testing List Sessions ---")
    try:
        response = requests.get(f"{BASE_URL}/sessions")
        response.raise_for_status()
        print(f"Status Code: {response.status_code}")
        sessions = response.json()
        print(f"Found {len(sessions)} sessions.")
        if sessions:
            print(f"First session: {json.dumps(sessions[0], indent=2)}")
    except Exception as e:
        print(f"List sessions failed: {e}")

def test_chat(message: str, session_id: str = None, image_path: str = None):
    """Tests the /chat endpoint."""
    print(f"\n--- Testing Chat: '{message}' ---")
    
    payload = {
        "message": message,
        "session_id": session_id
    }
    
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            payload["image_base64"] = f"data:image/jpeg;base64,{encoded_string}"
    
    try:
        response = requests.post(f"{BASE_URL}/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"Status Code: {response.status_code}")
        print(f"Butler Reply: {data['reply']}")
        print(f"Session ID: {data['session_id']}")
        return data['session_id']
    except Exception as e:
        print(f"Chat failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Details: {e.response.text}")
        return None

if __name__ == "__main__":
    print("Butler API Test Script")
    
    # 1. Health check
    test_health()
    
    # 2. Basic chat
    sid = test_chat("Hello Kuro! Who are you?")
    
    # 3. Follow-up chat in the same session
    if sid:
        test_chat("Can you tell me more about your architecture?", session_id=sid)
    
    # 4. List sessions
    test_list_sessions()

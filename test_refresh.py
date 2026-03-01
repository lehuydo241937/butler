import json
import requests
from datetime import datetime, timezone

def refresh_token(token_data):
    url = token_data.get("token_uri", "https://oauth2.googleapis.com/token")
    payload = {
        "client_id": token_data["client_id"],
        "client_secret": token_data["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "grant_type": "refresh_token",
    }
    
    print(f"Attempting to refresh token at {url}...")
    try:
        response = requests.post(url, data=payload, timeout=20)
        if response.status_code == 200:
            new_token = response.json()
            print("SUCCESS: Token refreshed successfully!")
            print(json.dumps(new_token, indent=2))
            return new_token
        else:
            print(f"FAILURE: Status code {response.status_code}")
            print(response.text)
            return None
    except requests.exceptions.Timeout:
        print("FAILURE: Request timed out (20s timeout)")
    except requests.exceptions.RequestException as e:
        print(f"FAILURE: Request exception: {e}")
    except Exception as e:
        print(f"FAILURE: Unexpected error: {e}")
    return None

if __name__ == "__main__":
    token_data = {
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "1091232162131-t6ts870l3g9uo2u5jntufssvn9gi3gfc.apps.googleusercontent.com",
        "client_secret": "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",
        "refresh_token": "1//0e-NqlhQclEbSCgYIARAAGA4SNwF-L9IrnF-M4BYKwS6ofvRTMZh1gI5DAgGAUHZcg5a_HpUgUGuvtZRcwn4uhpuTQLkdjdlVfWY"
    }
    
    refresh_token(token_data)

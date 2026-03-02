
import os
import sys
from google import genai
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.getcwd())

from secrets_manager.redis_secrets import RedisSecretsManager

load_dotenv()

def list_models():
    secrets = RedisSecretsManager()
    api_key = secrets.get_secret("gemini")
    
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
        
    if not api_key:
        print("GEMINI_API_KEY not found in Redis or .env")
        return
        
    client = genai.Client(api_key=api_key)
    print("Available embedding models:")
    try:
        for model in client.models.list():
            print(f"- {model.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    list_models()


import os
import sys
from google import genai
from dotenv import load_dotenv

sys.path.append(os.getcwd())
from secrets_manager.redis_secrets import RedisSecretsManager

load_dotenv()

def test_embed():
    secrets = RedisSecretsManager()
    api_key = secrets.get_secret("gemini") or os.getenv("GEMINI_API_KEY")
    
    client = genai.Client(api_key=api_key)
    
    models_to_test = [
        "text-embedding-004",
        "models/text-embedding-004",
        "gemini-embedding-001",
        "models/gemini-embedding-001",
        "text-embedding-004-model",
        "embedding-001"
    ]
    
    for m in models_to_test:
        try:
            print(f"Testing model: {m}")
            response = client.models.embed_content(
                model=m,
                contents="testing embedding"
            )
            print(f"SUCCESS with {m}! Vector size: {len(response.embeddings[0].values)}")
        except Exception as e:
            print(f"FAILED with {m}: {e}\n")

if __name__ == "__main__":
    test_embed()

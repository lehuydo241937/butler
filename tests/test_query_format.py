
import os
import sys

sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
from agent.vector_db import VectorDB
from google import genai
from backend.secrets_manager.redis_secrets import RedisSecretsManager

def test_query():
    secrets = RedisSecretsManager()
    api_key = secrets.get_secret("gemini") or os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents="Adecco",
        config={'task_type': 'retrieval_query'}
    )
    vector = response.embeddings[0].values
    
    vdb = VectorDB()
    try:
        results = vdb.client.query_points(
            collection_name=vdb.collection_name,
            query=vector,
            limit=2
        )
        with open("query_format.txt", "w", encoding="utf-8") as f:
            f.write(str(type(results)) + "\n")
            if hasattr(results, 'points'):
                f.write("Has points attribute.\n")
                for pt in results.points:
                    f.write(f"ID: {pt.id}, Score: {pt.score}, Payload keys: {list(pt.payload.keys())}\n")
            else:
                f.write("No 'points' attribute found.\n")
    except Exception as e:
        with open("query_format.txt", "w", encoding="utf-8") as f:
            f.write(f"Error: {e}\n")

if __name__ == "__main__":
    test_query()

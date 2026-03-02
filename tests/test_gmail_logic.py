
import os
import sys
import uuid

# Add current directory to path so we can import agent modules
sys.path.append(os.getcwd())
# Ensure console can print utf-8
sys.stdout.reconfigure(encoding='utf-8')

from agent.vector_db import VectorDB
from agent.gmail_tools import GmailTools
from secrets_manager.redis_secrets import RedisSecretsManager
from google import genai
from qdrant_client.http import models

def run_test():
    secrets = RedisSecretsManager()
    
    # 1. Get emails
    print("--- 1. Getting latest 5 emails ---")
    gmail = GmailTools(secrets)
    emails = gmail.list_emails(max_results=5)
    
    if not emails or (len(emails) > 0 and "error" in emails[0]):
        print(f"Error getting emails: {emails}")
        return
        
    for i, e in enumerate(emails):
        print(f"Email {i+1} Subject: {e.get('subject')}")
        
    if len(emails) < 5:
        print(f"Warning: Only found {len(emails)} emails in inbox. Test expects 5.")
        
    # 2. Vectorize them
    print("\n--- 2. Vectorizing emails ---")
    api_key = secrets.get_secret("gemini") or os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    vectors_data = []
    vector_db = VectorDB()
    
    for i, e in enumerate(emails):
        subject = e.get('subject', '')
        full = gmail.get_email(e["id"])
        body = full.get("body", e.get("snippet", "")) if "error" not in full else e.get("snippet", "")
        text = f"Subject: {subject}\n\n{body}"
        
        try:
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config={'task_type': 'retrieval_document'}
            )
            vector = response.embeddings[0].values
            vectors_data.append({"email": e, "text": text, "vector": vector})
            print(f"[{i+1}] Success vectorizing '{subject}'. Vector dimensions: {len(vector)}")
        except Exception as ex:
            print(f"[{i+1}] Failed vectorizing '{subject}': {ex}")

    # 3. Add to vector database
    print("\n--- 3. Adding to vector database ---")
    
    # Clear the collection before adding, to ensure count is accurate for this run
    try:
        vector_db.client.delete_collection(vector_db.collection_name)
        vector_db._ensure_collection() # Recreates it
        print("Cleared existing collection prior to test.")
    except Exception as ex:
        print(f"Note: Could not clear existing collection: {ex}")
        
    for i, data in enumerate(vectors_data):
        e = data["email"]
        text = data["text"]
        vector = data["vector"]
        
        # Generate deterministic UUID from Gmail ID
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, e["id"]))
        
        metadata = {
            "subject": e.get("subject"),
            "from": e.get("from"),
            "date": e.get("date")
        }
        
        try:
            vector_db.client.upsert(
                collection_name=vector_db.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "email_id": e["id"],
                            "text": text[:1000],
                            **metadata
                        }
                    )
                ]
            )
            print(f"[{i+1}] Success adding '{e.get('subject')}' to Qdrant. Point ID: {point_id}")
        except Exception as ex:
            print(f"[{i+1}] Failed adding '{e.get('subject')}' to Qdrant: {ex}")

    # 4 & 5. Count vectorized emails
    print("\n--- 4. Counting vectorized emails in DB ---")
    try:
        collection_info = vector_db.client.get_collection(vector_db.collection_name)
        count = collection_info.points_count
        print(f"Total emails properly vectorized and stored in '{vector_db.collection_name}': {count}")
        
        print("\n--- 5. Test Result ---")
        if count == 5:
            print("✅ TEST PASSED: Count is exactly 5.")
        else:
            print(f"❌ TEST FAILED: Count is {count}, expected 5.")
    except Exception as ex:
        print(f"Failed to get collection count: {ex}")

if __name__ == "__main__":
    run_test()

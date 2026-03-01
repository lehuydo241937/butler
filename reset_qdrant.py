
import os
import sys
from qdrant_client import QdrantClient

# Add current directory to path so we can import agent modules
sys.path.append(os.getcwd())

from agent.vector_db import VectorDB

def reset_collection():
    try:
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", 6333))
        client = QdrantClient(host=host, port=port)
        
        # Verify if exists and delete
        collections = client.get_collections().collections
        exists = any(c.name == "emails" for c in collections)
        
        if exists:
            print("Deleting existing 'emails' collection (size 768)...")
            client.delete_collection("emails")
            print("Deleted successfully.")
        
        # Now init VectorDB to recreate it with the correct size (3072)
        print("Recreating collection through VectorDB class...")
        vdb = VectorDB(host=host, port=port)
        
        collection_info = vdb.client.get_collection("emails")
        print(f"Recreated successfully.")
        print(f"Collection size configured to: {collection_info.config.params.vectors.size}")
            
    except Exception as e:
        print(f"Error resetting Qdrant collection: {e}")

if __name__ == "__main__":
    reset_collection()

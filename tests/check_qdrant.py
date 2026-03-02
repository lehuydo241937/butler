
import os
import sys
from qdrant_client import QdrantClient

# Add current directory to path so we can import agent modules
sys.path.append(os.getcwd())

from agent.vector_db import VectorDB

def check():
    try:
        vdb = VectorDB()
        collection_info = vdb.client.get_collection(vdb.collection_name)
        print(f"Collection Name: {vdb.collection_name}")
        print(f"Status: {collection_info.status}")
        print(f"Points count: {collection_info.points_count}")
        
        # List some points
        if collection_info.points_count > 0:
            scroll_result = vdb.client.scroll(
                collection_name=vdb.collection_name,
                limit=5,
                with_payload=True
            )
            print("\nRecent 5 points:")
            for point in scroll_result[0]:
                payload = point.payload
                print(f"ID: {point.id}")
                print(f"  Subject: {payload.get('subject')}")
                print(f"  From: {payload.get('from')}")
                print(f"  Date: {payload.get('date')}")
                print("-" * 20)
        else:
            print("No emails indexed yet.")
            
    except Exception as e:
        print(f"Error checking Qdrant: {e}")

if __name__ == "__main__":
    check()

import os
import sys
import zipfile
import json
import shutil
from io import BytesIO

sys.path.append(os.getcwd())
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from agent.butler import ButlerAgent
from agent.data_ingester import DataIngester

def create_mock_fb_zip():
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        # FB structure: messages/inbox/thread_name/message_1.json
        fb_data = {
            "title": "John Doe",
            "messages": [
                {
                    "sender_name": "John Doe",
                    "timestamp_ms": 1709376000000,
                    "content": "Hey, are we still meeting for lunch at 12?"
                },
                {
                    "sender_name": "Me",
                    "timestamp_ms": 1709376060000,
                    "content": "Yes, see you at the cafe."
                }
            ]
        }
        z.writestr("messages/inbox/johndoe_123/message_1.json", json.dumps(fb_data))
    buf.seek(0)
    return buf

def create_mock_zalo_zip():
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        # Zalo structure (mocking the JSON search logic I implemented)
        zalo_data = [
            {
                "from": "Alice",
                "timestamp": 1709377000,
                "message": "Don't forget the files for the presentation."
            }
        ]
        z.writestr("Zalo_Export/messages/alice_123.json", json.dumps(zalo_data))
        z.writestr("message.html", "<html>Mock</html>") # For detection
    buf.seek(0)
    return buf

def verify():
    print("🚀 Starting verification...")
    agent = ButlerAgent()
    
    # 1. Test FB Ingestion
    print("\n--- Testing Facebook Ingestion ---")
    fb_zip = create_mock_fb_zip()
    res_fb = agent.ingester.process_zip(fb_zip, filename="mock_fb.zip")
    print(f"Result: {res_fb}")
    
    # 2. Test Zalo Ingestion
    print("\n--- Testing Zalo Ingestion ---")
    zalo_zip = create_mock_zalo_zip()
    res_zalo = agent.ingester.process_zip(zalo_zip, filename="mock_zalo.zip")
    print(f"Result: {res_zalo}")
    
    # 3. Test Semantic Search
    print("\n--- Testing Semantic Search (FB) ---")
    search_fb = agent.semantic_search_messages("lunch at 12", source="facebook")
    print(search_fb)
    
    print("\n--- Testing Semantic Search (Zalo) ---")
    search_zalo = agent.semantic_search_messages("presentation files", source="zalo")
    print(search_zalo)
    
    print("\n--- Testing All Search ---")
    search_all = agent.semantic_search_messages("meeting")
    print(search_all)

if __name__ == "__main__":
    verify()

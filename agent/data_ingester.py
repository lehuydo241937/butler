import os
import zipfile
import json
import logging
import shutil
import tempfile
from typing import List, Dict, Any, Optional, Union
from io import BytesIO
from google import genai
from agent.vector_db import VectorDB
from agent.db_manager import DBManager

logger = logging.getLogger(__name__)

class DataIngester:
    """Handles extraction and vectorization of Zalo/FB message data."""

    def __init__(self, db: DBManager, vector_db: VectorDB, genai_client: genai.Client):
        self.db = db
        self.vector_db = vector_db
        self.genai_client = genai_client

    def is_file_processed(self, filename: str) -> bool:
        """Checks if a file has already been processed."""
        res = self.db.query("SELECT 1 FROM processed_files WHERE filename = ?", (filename,))
        return len(res) > 0

    def mark_file_processed(self, filename: str, source: str):
        """Marks a file as processed in the database."""
        self.db.execute_raw_query(
            "INSERT INTO processed_files (filename, source) VALUES (?, ?)", 
            (filename, source)
        )

    def process_zip(self, zip_source: Union[str, BytesIO], filename: str = None) -> Dict[str, Any]:
        """
        Processes a ZIP file (path or BytesIO).
        Detects type, Extracts, Parses, and Vectorizes.
        """
        if filename and self.is_file_processed(filename):
            logger.info(f"File {filename} already processed. Skipping.")
            return {"status": "skipped", "message": f"File {filename} already processed."}

        temp_dir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(zip_source, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Detect format
            source_type = self._detect_source_type(temp_dir)
            if not source_type:
                return {"status": "error", "message": "Could not detect Zalo or Facebook format in ZIP."}

            # Parse
            messages = []
            if source_type == "zalo":
                messages = self._parse_zalo(temp_dir)
            elif source_type == "facebook":
                messages = self._parse_facebook(temp_dir)

            if not messages:
                return {"status": "error", "message": f"No messages found in {source_type} export."}

            # Vectorize
            indexed_count = self._vectorize_messages(messages, source_type)

            if filename:
                self.mark_file_processed(filename, source_type)

            return {
                "status": "success", 
                "source": source_type, 
                "count": indexed_count,
                "message": f"Successfully indexed {indexed_count} messages from {source_type}."
            }

        except Exception as e:
            logger.error(f"Error processing ZIP: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            shutil.rmtree(temp_dir)

    def _detect_source_type(self, path: str) -> Optional[str]:
        """Detects if the extracted content is Zalo or Facebook."""
        # Simple detection based on common files/folders
        # Zalo often has 'message.html' or 'messages/' folder with numeric IDs
        # Facebook has 'messages/' folder with 'inbox/', 'archived_threads/', etc.
        
        items = os.listdir(path)
        
        # Check Facebook
        if "messages" in items and os.path.isdir(os.path.join(path, "messages")):
            m_path = os.path.join(path, "messages")
            if "inbox" in os.listdir(m_path):
                return "facebook"

        # Check Zalo
        # Zalo exports vary, but often have a structure like 'Zalo_Message_...' 
        # inside which there's a 'message' folder or 'message.html'
        for root, dirs, files in os.walk(path):
            if "message.html" in files:
                return "zalo"
            if any(d.isdigit() for d in dirs) and "messages" in root.lower():
                return "zalo"

        return None

    def _parse_facebook(self, path: str) -> List[Dict[str, Any]]:
        """Parses Facebook JSON messages."""
        messages = []
        inbox_path = os.path.join(path, "messages", "inbox")
        if not os.path.exists(inbox_path):
            return []

        for thread_dir in os.listdir(inbox_path):
            thread_path = os.path.join(inbox_path, thread_dir)
            if not os.path.isdir(thread_path):
                continue
            
            for filename in os.listdir(thread_path):
                if filename.startswith("message_") and filename.endswith(".json"):
                    with open(os.path.join(thread_path, filename), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        thread_name = data.get("title", "Unknown")
                        for msg in data.get("messages", []):
                            content = msg.get("content")
                            if content:
                                # Fix encoding if needed (FB sometimes uses mangled UTF-8)
                                try:
                                    content = content.encode('latin1').decode('utf-8')
                                    sender = msg.get("sender_name", "Unknown").encode('latin1').decode('utf-8')
                                except:
                                    sender = msg.get("sender_name", "Unknown")
                                
                                timestamp = msg.get("timestamp_ms", 0) / 1000
                                messages.append({
                                    "id": f"fb_{msg.get('timestamp_ms')}_{sender}",
                                    "text": f"From: {sender} (Thread: {thread_name})\n\n{content}",
                                    "metadata": {
                                        "sender": sender,
                                        "thread": thread_name,
                                        "timestamp": timestamp,
                                        "source": "facebook"
                                    }
                                })
        return messages

    def _parse_zalo(self, path: str) -> List[Dict[str, Any]]:
        """Parses Zalo data. Since Zalo often exports to HTML, we might need a basic parser."""
        # Note: True Zalo parsing can be complex if it's only HTML. 
        # If there are JSONs in 'messages/' folder, it's easier.
        messages = []
        # Search for JSON files in any 'messages' or numeric folders
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith(".json"):
                    try:
                        with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # Zalo JSON structure varies, but let's assume a list of messages
                            # for a basic implementation. Custom logic might be needed for specific schemas.
                            if isinstance(data, list):
                                for item in data:
                                    text = item.get("message") or item.get("content")
                                    if text:
                                        sender = item.get("from") or item.get("senderName") or "Unknown"
                                        ts = item.get("timestamp") or 0
                                        messages.append({
                                            "id": f"zalo_{ts}_{sender}",
                                            "text": f"From: {sender}\n\n{text}",
                                            "metadata": {
                                                "sender": sender,
                                                "timestamp": ts,
                                                "source": "zalo"
                                            }
                                        })
                    except:
                        continue
        return messages

    def _vectorize_messages(self, messages: List[Dict[str, Any]], source: str) -> int:
        """Batch vectorizes messages into Qdrant."""
        indexed_count = 0
        collection_name = source # "zalo" or "facebook"
        
        for msg in messages:
            success = self.vector_db.upsert_document(
                collection_name=collection_name,
                doc_id=msg["id"],
                text=msg["text"],
                metadata=msg["metadata"],
                genai_client=self.genai_client
            )
            if success:
                indexed_count += 1
                
        return indexed_count

    def scan_folder(self, folder_path: str) -> Dict[str, Any]:
        """Scans a folder for new ZIP files and processes them."""
        results = []
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            return {"status": "info", "message": f"Created folder {folder_path}. No files to process yet."}

        for file in os.listdir(folder_path):
            if file.endswith(".zip"):
                zip_path = os.path.join(folder_path, file)
                res = self.process_zip(zip_path, filename=file)
                results.append(res)
        
        return {"status": "complete", "results": results}

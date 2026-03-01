import os
import logging
import uuid
from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from google import genai

logger = logging.getLogger(__name__)

class VectorDB:
    """Manages semantic search and vector storage using Qdrant."""

    def __init__(self, host: str = "localhost", port: int = 6333, collection_name: str = "emails"):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.client = QdrantClient(host=host, port=port)
        self._ensure_collection()

    def _ensure_collection(self):
        """Creates the collection if it does not exist."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=3072,  # gemini-embedding-001 size
                        distance=models.Distance.COSINE
                    )
                )
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant or create collection: {e}")

    def list_collections(self) -> List[str]:
        """Returns a list of all collection names in Qdrant."""
        try:
            collections = self.client.get_collections().collections
            return [c.name for c in collections]
        except Exception as e:
            logger.error(f"Failed to list Qdrant collections: {e}")
            return []

    def upsert_email(self, email_id: str, text: str, metadata: Dict[str, Any], genai_client: genai.Client):
        """Generates an embedding and upserts proof into Qdrant."""
        try:
            # Generate embedding
            response = genai_client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config={'task_type': 'retrieval_document'}
            )
            vector = response.embeddings[0].values

            # Generate deterministic UUID from Gmail ID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, email_id))

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "email_id": email_id,
                            "text": text[:1000],  # Store snippet for context
                            **metadata
                        }
                    )
                ]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert email {email_id} to Qdrant: {e}")
            return False

    def search_emails(self, query: str, genai_client: genai.Client, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches for relevant emails based on query string."""
        try:
            # Generate query embedding
            response = genai_client.models.embed_content(
                model="gemini-embedding-001",
                contents=query,
                config={'task_type': 'retrieval_query'}
            )
            vector = response.embeddings[0].values

            # Search Qdrant
            query_response = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit
            )
            results = query_response.points

            return [
                {
                    "email_id": hit.payload.get("email_id"),
                    "score": hit.score,
                    "text": hit.payload.get("text"),
                    "subject": hit.payload.get("subject"),
                    "from": hit.payload.get("from"),
                    "date": hit.payload.get("date")
                }
                for hit in results
            ]
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

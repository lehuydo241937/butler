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

    def __init__(self, host: str = "localhost", port: int = 6333):
        self.host = host
        self.port = port
        self.client = QdrantClient(host=host, port=port)

    def _ensure_collection(self, collection_name: str, vector_size: int = 3072):
        """Creates the collection if it does not exist."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)
            if not exists:
                logger.info(f"Creating Qdrant collection: {collection_name}")
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,  # gemini-embedding-001 size
                        distance=models.Distance.COSINE
                    )
                )
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant or create collection {collection_name}: {e}")

    def list_collections(self) -> List[str]:
        """Returns a list of all collection names in Qdrant."""
        try:
            collections = self.client.get_collections().collections
            return [c.name for c in collections]
        except Exception as e:
            logger.error(f"Failed to list Qdrant collections: {e}")
            return []

    def upsert_document(self, collection_name: str, doc_id: str, text: str, metadata: Dict[str, Any], genai_client: genai.Client):
        """Generates an embedding and upserts a document into Qdrant."""
        try:
            self._ensure_collection(collection_name)
            
            # Generate embedding
            response = genai_client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config={'task_type': 'retrieval_document'}
            )
            vector = response.embeddings[0].values

            # Generate deterministic UUID from doc_id
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "doc_id": doc_id,
                            "text": text[:2000],  # Store more context for messages
                            **metadata
                        }
                    )
                ]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert document {doc_id} to collection {collection_name}: {e}")
            return False

    def search_documents(self, collection_name: str, query: str, genai_client: genai.Client, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches for relevant documents in a specific collection."""
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
                collection_name=collection_name,
                query=vector,
                limit=limit
            )
            results = query_response.points

            return [
                {
                    "score": hit.score,
                    **hit.payload
                }
                for hit in results
            ]
        except Exception as e:
            logger.error(f"Qdrant search failed in {collection_name}: {e}")
            return []

    # Backward compatibility helpers
    def upsert_email(self, email_id: str, text: str, metadata: Dict[str, Any], genai_client: genai.Client):
        # Add email_id to payload for backward compat if needed, though metadata usually has it
        metadata["email_id"] = email_id
        return self.upsert_document("emails", email_id, text, metadata, genai_client)

    def search_emails(self, query: str, genai_client: genai.Client, limit: int = 5) -> List[Dict[str, Any]]:
        return self.search_documents("emails", query, genai_client, limit)


from qdrant_client import QdrantClient
import inspect

client = QdrantClient()
print(inspect.signature(client.query_points))


from qdrant_client import QdrantClient

client = QdrantClient()
print("Methods on QdrantClient:")
for attr in dir(client):
    if not attr.startswith("_"):
        print(attr)

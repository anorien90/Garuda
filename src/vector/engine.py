import uuid
from typing import List, Dict, Any, Optional

from .base import VectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels



class QdrantVectorStore(VectorStore):
    def __init__(self, url: str = "http://qdrant:6333", collection: str = "pages", vector_size: int = 384):
        self.client = QdrantClient(url=url)
        self.collection = collection
        self.vector_size = vector_size
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            self.client.get_collection(self.collection)
        except Exception:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
            )

    def upsert(self, point_id: str, vector: List[float], payload: Dict[str, Any]):
        try:
            uid = str(uuid.UUID(point_id))
        except ValueError:
            uid = str(uuid.uuid5(uuid.NAMESPACE_URL, point_id))

        self.client.upsert(
            collection_name=self.collection,
            points=[
                qmodels.PointStruct(
                    id=uid,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    def search(self, query_vector: List[float], top_k: int = 10, filter_: Optional[qmodels.Filter] = None):
        # Modern qdrant-client uses .search() or .query_points()
        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=filter_,
            limit=top_k,
        )
        return response.points

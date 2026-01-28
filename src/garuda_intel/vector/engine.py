import uuid
import logging
from typing import List, Dict, Any, Optional

from .base import VectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


def point_id_for_page(url: str) -> str:
    """Use deterministic UUID for pages so SQL/Qdrant stay aligned."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


class QdrantVectorStore(VectorStore):
    def __init__(self, url: str = "http://qdrant:6333", collection: str = "pages", vector_size: int = 384):
        self.logger = logging.getLogger(__name__)
        self.client = QdrantClient(url=url)
        self.collection = collection
        self.vector_size = vector_size
        self._ensure_collection()
        self.logger.info(f"QdrantVectorStore initialized: url={url}, collection={collection}, vector_size={vector_size}")

    def _ensure_collection(self):
        try:
            self.client.get_collection(self.collection)
            self.logger.info(f"Using existing Qdrant collection: {self.collection}")
        except Exception:
            self.logger.info(f"Creating new Qdrant collection: {self.collection}")
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
        # Log at debug level for individual upserts, info level handled by caller
        self.logger.debug(f"Upserted embedding to Qdrant: collection={self.collection}, point_id={uid}, payload_type={payload.get('type', 'unknown')}")

    def search(self, query_vector: List[float], top_k: int = 10, filter_: Optional[qmodels.Filter] = None):
        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=filter_,
            limit=top_k,
        )
        return response.points

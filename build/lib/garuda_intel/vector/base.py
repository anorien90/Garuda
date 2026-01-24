from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from qdrant_client.http import models as qmodels



class VectorStore(ABC):
    
    @abstractmethod
    def upsert(self, point_id: str, vector: List[float], payload: Dict[str, Any]): ...
    

    @abstractmethod
    def search(self, query_vector: List[float], top_k: int = 10, filter_: Optional[qmodels.Filter] = None): ...



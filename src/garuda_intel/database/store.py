import abc
from typing import List, Dict, Optional, Any
from ..types.page.fingerprint import PageFingerprint


class PersistenceStore(abc.ABC):
    @abc.abstractmethod
    def save_seed(self, query: str, entity_type: str, source: str) -> str: ...
    @abc.abstractmethod
    def save_page(self, page: Dict) -> str: ...
    @abc.abstractmethod
    def save_links(self, from_url: str, links: List[Dict]): ...
    @abc.abstractmethod
    def save_fingerprint(self, fp: PageFingerprint): ...
    @abc.abstractmethod
    def save_patterns(self, patterns: List[Dict]): ...
    @abc.abstractmethod
    def save_domains(self, domains: List[Dict]): ...
    @abc.abstractmethod
    def save_entities(self, entities: List[Dict]) -> Dict[tuple, str]: ...
    @abc.abstractmethod
    def get_all_pages(self, q: Optional[str] = None, entity_type: Optional[str] = None,
                      page_type: Optional[str] = None, min_score: Optional[float] = None,
                      sort: str = "fresh", limit: int = 200) -> List[Any]: ...
    @abc.abstractmethod
    def get_page_by_url(self, url: str) -> Optional[Dict]: ...
    @abc.abstractmethod
    def get_page_content_by_url(self, url: str) -> Optional[Dict]: ...
    @abc.abstractmethod
    def get_intelligence(self, entity_id: Optional[str] = None,
                         min_confidence: float = 0.0, limit: int = 100) -> List[Dict]: ...
    @abc.abstractmethod
    def search_intelligence_data(self, query: str) -> List[Dict]: ...
    @abc.abstractmethod
    def search_intel(self, keyword: str, limit: int = 50,
                     entity_type: Optional[str] = None, page_type: Optional[str] = None) -> List[Dict]: ...
    @abc.abstractmethod
    def get_aggregated_entity_data(self, entity_name: str) -> Dict[str, Any]: ...
    @abc.abstractmethod
    def get_entities(self, name_like: Optional[str] = None, kind: Optional[str] = None,
                     limit: int = 100) -> List[Dict]: ...
    @abc.abstractmethod
    def get_pending_refresh(self, limit: int = 50) -> List[Dict]: ...
    @abc.abstractmethod
    def mark_visited(self, url: str): ...
    @abc.abstractmethod
    def has_visited(self, url: str) -> bool: ...

    # -- Semantic snippet helpers ------------------------------------------

    def search_snippets(self, keyword: str, limit: int = 20) -> List[Dict]:
        """Keyword search over the semantic_snippets table.

        Default implementation returns an empty list so that stores without
        snippet support continue to work.
        """
        return []

    def get_neighbouring_snippets(
        self,
        page_id: str,
        chunk_index: int,
        direction: str = "both",
        window: int = 2,
    ) -> List[Dict]:
        """Fetch neighbouring snippets by *page_id* and *chunk_index*.

        Args:
            page_id: The page UUID that owns the snippets.
            chunk_index: The centre snippet's index.
            direction: ``'prev'``, ``'next'``, or ``'both'``.
            window: How many extra snippets to fetch in each direction.

        Returns:
            List of snippet dicts ordered by ``chunk_index``.
        """
        return []

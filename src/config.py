from enum import Enum
from typing import Optional, Dict, Any


class Settings:
    def __init__(
        self,
        entity_type: EntityType = EntityType.COMPANY,
        use_selenium: bool = True,
        use_sqlite: bool = False,
        sqlite_path: str = "crawler.db",
        max_pages_per_domain: int = 50,
        max_total_pages: int = 1000,
        score_threshold: float = 25.0,
        refresh_only: bool = False,
        llm_pattern_refresh: bool = False,
    ):
        self.entity_type = entity_type
        self.use_selenium = use_selenium
        self.use_sqlite = use_sqlite
        self.sqlite_path = sqlite_path
        self.max_pages_per_domain = max_pages_per_domain
        self.max_total_pages = max_total_pages
        self.score_threshold = score_threshold
        self.refresh_only = refresh_only
        self.llm_pattern_refresh = llm_pattern_refresh

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__

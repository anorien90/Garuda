from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from .type import EntityType


@dataclass
class EntityProfile:
    name: str
    entity_type: EntityType
    aliases: List[str] = field(default_factory=list)
    location_hint: str = ""
    official_domains: List[str] = field(default_factory=list)
    data_gaps: List[str] = field(default_factory=list)
    completeness_score: float = 0.0
    last_enrichment: Optional[datetime] = None

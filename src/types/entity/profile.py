from dataclasses import dataclass, field
from typing import List, Optional
from .type import EntityType


@dataclass
class EntityProfile:
    name: str
    entity_type: EntityType
    aliases: List[str] = field(default_factory=list)
    location_hint: str = ""
    official_domains: List[str] = field(default_factory=list)

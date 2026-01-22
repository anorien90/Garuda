from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class EntityType(str, Enum):
    COMPANY = "company"
    PERSON = "person"
    NEWS = "news"
    TOPIC = "topic"


@dataclass
class EntityProfile:
    name: str
    entity_type: EntityType
    aliases: List[str] = field(default_factory=list)
    location_hint: str = ""
    official_domains: List[str] = field(default_factory=list)

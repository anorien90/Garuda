from enum import Enum


class EntityType(str, Enum):
    COMPANY = "company"
    PERSON = "person"
    NEWS = "news"
    TOPIC = "topic"

"""Database utility functions."""
import json
import uuid


def uuid5_url(value: str) -> str:
    """Generate deterministic UUID5 from URL."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def uuid4() -> str:
    """Generate random UUID4."""
    return str(uuid.uuid4())


def as_dict(obj):
    """Parse object to dictionary.
    
    Args:
        obj: Can be None, str (JSON), or dict
        
    Returns:
        Dictionary representation or empty dict
    """
    if obj is None:
        return {}
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except Exception:
            return {}
    if isinstance(obj, dict):
        return obj
    return {}

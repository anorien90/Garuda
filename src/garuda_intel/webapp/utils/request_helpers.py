"""Request parameter parsing utilities."""

import logging

logger = logging.getLogger(__name__)


def safe_int(value, default=0):
    """
    Safely parse integer from request args, handling binary data and invalid input.
    
    Args:
        value: Value to parse (typically from request.args.get())
        default: Default value to return if parsing fails
        
    Returns:
        Parsed integer or default value
    """
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse int from value: {repr(value)[:100]}")
        return default


def safe_float(value, default=0.0):
    """
    Safely parse float from request args, handling binary data and invalid input.
    
    Args:
        value: Value to parse (typically from request.args.get())
        default: Default value to return if parsing fails
        
    Returns:
        Parsed float or default value
    """
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse float from value: {repr(value)[:100]}")
        return default

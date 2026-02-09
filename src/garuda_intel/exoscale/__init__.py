"""Exoscale cloud integration for remote Ollama instances.

This module provides integration with Exoscale cloud to run Ollama instances
remotely, with automatic lifecycle management, idle shutdown, and secure access.
"""

from .adapter import ExoscaleOllamaAdapter

__all__ = ["ExoscaleOllamaAdapter"]

"""API source adapter for REST and GraphQL endpoints.

This adapter fetches intelligence from web APIs, supporting both REST and GraphQL,
with automatic response normalization.
"""

import hashlib
import json
from typing import List, Dict, Any, Optional
from enum import Enum
import requests

from .base_adapter import (
    SourceAdapter,
    Document,
    SourceType,
    FetchError,
    NormalizationError,
)


class APIType(Enum):
    """Type of API."""
    REST = "rest"
    GRAPHQL = "graphql"


class APIAdapter(SourceAdapter):
    """Adapter for fetching data from REST and GraphQL APIs.
    
    Features:
    - Support for REST APIs (GET, POST)
    - Support for GraphQL queries
    - Automatic JSON response normalization
    - Header and authentication support
    - Response pagination handling
    - Configurable retry logic
    
    Configuration:
        api_type: Type of API ("rest" or "graphql")
        base_url: Base URL for API endpoints
        auth_token: Optional authentication token
        headers: Optional custom headers
        timeout_seconds: Request timeout (default: 30)
        max_retries: Maximum retry attempts (default: 3)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize API adapter.
        
        Args:
            config: Configuration dict with keys:
                - api_type (str): "rest" or "graphql"
                - base_url (str): API base URL
                - auth_token (str): Optional auth token
                - headers (dict): Optional headers
                - timeout_seconds (int): Request timeout
                - max_retries (int): Max retry attempts
        """
        super().__init__(config)
        
        api_type_str = self.config.get("api_type", "rest")
        self.api_type = APIType(api_type_str)
        self.base_url = self.config.get("base_url", "")
        self.timeout = self.config.get("timeout_seconds", 30)
        self.max_retries = self.config.get("max_retries", 3)
        
        # Build headers
        self.headers = self.config.get("headers", {}).copy()
        auth_token = self.config.get("auth_token")
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        
        # Ensure Content-Type header
        if "Content-Type" not in self.headers:
            self.headers["Content-Type"] = "application/json"
    
    def fetch(self, query: str, **kwargs) -> List[Document]:
        """Fetch data from API.
        
        Args:
            query: For REST: endpoint path, For GraphQL: query string
            **kwargs: Additional parameters:
                - method (str): HTTP method for REST (default: GET)
                - params (dict): Query parameters for REST
                - variables (dict): Variables for GraphQL
                - body (dict): Request body for REST POST
                
        Returns:
            List of normalized Documents
            
        Raises:
            FetchError: If API request fails
        """
        # Check cache
        cache_key = self._make_cache_key(query, kwargs)
        cached = self.get_from_cache(cache_key)
        if cached:
            return [cached]
        
        try:
            if self.api_type == APIType.REST:
                response_data = self._fetch_rest(query, **kwargs)
            else:
                response_data = self._fetch_graphql(query, **kwargs)
            
            # Normalize response
            document = self.normalize({
                "data": response_data,
                "query": query,
                "url": self._build_url(query),
            })
            
            # Cache result
            self.add_to_cache(cache_key, document)
            
            return [document]
            
        except Exception as e:
            raise FetchError(f"Failed to fetch from API: {str(e)}")
    
    def normalize(self, raw_data: Any) -> Document:
        """Normalize API response into a Document.
        
        Args:
            raw_data: Dict with keys:
                - data: API response data (dict or list)
                - query: Query string or endpoint
                - url: Full request URL
                
        Returns:
            Normalized Document object
            
        Raises:
            NormalizationError: If normalization fails
        """
        try:
            data = raw_data["data"]
            query = raw_data["query"]
            url = raw_data["url"]
            
            # Convert data to text content
            content = self._extract_content(data)
            
            # Extract title from data if possible
            title = self._extract_title(data, query)
            
            # Generate ID
            doc_id = self._generate_id(url)
            
            # Build metadata
            metadata = {
                "api_type": self.api_type.value,
                "query": query,
                "data_type": type(data).__name__,
            }
            
            # Add data structure info
            if isinstance(data, dict):
                metadata["keys"] = list(data.keys())
            elif isinstance(data, list):
                metadata["count"] = len(data)
            
            return Document(
                id=doc_id,
                source_type=SourceType.API,
                url=url,
                title=title,
                content=content,
                metadata=metadata,
                confidence=0.9  # API data is generally high quality
            )
            
        except Exception as e:
            raise NormalizationError(f"Failed to normalize API response: {str(e)}")
    
    def _fetch_rest(self, endpoint: str, **kwargs) -> Any:
        """Fetch data from REST API.
        
        Args:
            endpoint: API endpoint path
            **kwargs: Parameters (method, params, body)
            
        Returns:
            Parsed JSON response
        """
        method = kwargs.get("method", "GET").upper()
        params = kwargs.get("params", {})
        body = kwargs.get("body")
        
        url = self._build_url(endpoint)
        
        for attempt in range(self.max_retries):
            try:
                if method == "GET":
                    response = requests.get(
                        url,
                        params=params,
                        headers=self.headers,
                        timeout=self.timeout
                    )
                elif method == "POST":
                    response = requests.post(
                        url,
                        params=params,
                        json=body,
                        headers=self.headers,
                        timeout=self.timeout
                    )
                else:
                    raise FetchError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                return response.json()
                
            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise FetchError(f"REST request failed after {self.max_retries} attempts: {e}")
                # Retry on next iteration
        
        raise FetchError("Unexpected error in REST fetch")
    
    def _fetch_graphql(self, query: str, **kwargs) -> Any:
        """Fetch data from GraphQL API.
        
        Args:
            query: GraphQL query string
            **kwargs: Parameters (variables)
            
        Returns:
            Parsed GraphQL response data
        """
        variables = kwargs.get("variables", {})
        
        # GraphQL always POSTs to base URL
        url = self.base_url
        
        payload = {
            "query": query,
            "variables": variables
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                result = response.json()
                
                # Check for GraphQL errors
                if "errors" in result:
                    raise FetchError(f"GraphQL errors: {result['errors']}")
                
                return result.get("data", {})
                
            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise FetchError(f"GraphQL request failed after {self.max_retries} attempts: {e}")
        
        raise FetchError("Unexpected error in GraphQL fetch")
    
    def _build_url(self, endpoint: str) -> str:
        """Build full URL from base URL and endpoint.
        
        Args:
            endpoint: Endpoint path or full URL
            
        Returns:
            Complete URL
        """
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        
        base = self.base_url.rstrip("/")
        path = endpoint.lstrip("/")
        return f"{base}/{path}"
    
    def _extract_content(self, data: Any) -> str:
        """Extract text content from API data.
        
        Args:
            data: API response data
            
        Returns:
            Text representation of data
        """
        if isinstance(data, str):
            return data
        
        # Convert to formatted JSON
        try:
            return json.dumps(data, indent=2, ensure_ascii=False)
        except:
            return str(data)
    
    def _extract_title(self, data: Any, query: str) -> Optional[str]:
        """Try to extract a title from the data.
        
        Args:
            data: API response data
            query: Query string
            
        Returns:
            Extracted title or None
        """
        # Try common title fields
        if isinstance(data, dict):
            for key in ["title", "name", "subject", "heading"]:
                if key in data:
                    return str(data[key])
            
            # If data has a single top-level key, use it
            if len(data) == 1:
                return list(data.keys())[0]
        
        # Fall back to query
        return f"API: {query[:50]}"
    
    def _make_cache_key(self, query: str, kwargs: Dict) -> str:
        """Generate cache key from query and parameters.
        
        Args:
            query: Query string
            kwargs: Request parameters
            
        Returns:
            Cache key string
        """
        # Create deterministic key from query and params
        key_parts = [query]
        
        # Add relevant kwargs
        for k in ["method", "params", "variables", "body"]:
            if k in kwargs:
                key_parts.append(json.dumps(kwargs[k], sort_keys=True))
        
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _generate_id(self, url: str) -> str:
        """Generate unique ID for document.
        
        Args:
            url: Request URL
            
        Returns:
            Hash-based unique ID
        """
        return hashlib.md5(url.encode()).hexdigest()

"""
Content router that directs content to specialized processors based on type.
"""

import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

from .content_classifier import ContentType, ContentTypeClassifier
from .text_processor import TextProcessor


class ContentProcessor(ABC):
    """Base class for specialized content processors."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.text_processor = TextProcessor()
    
    @abstractmethod
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process content and extract relevant information.
        
        Args:
            html: Raw HTML content
            text: Cleaned text content
            metadata: Page metadata
            
        Returns:
            Processed content with extracted information
        """
        pass


class ArticleProcessor(ContentProcessor):
    """Specialized processor for news articles and blog posts."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract article-specific information."""
        result = {
            "content_type": "article",
            "title": metadata.get("title", ""),
            "text": text,
        }
        
        # Extract publication date from metadata or HTML
        if "article:published_time" in metadata:
            result["published_date"] = metadata["article:published_time"]
        
        # Extract author
        if "author" in metadata:
            result["author"] = metadata["author"]
        
        # Focus on main content, skip navigation/ads
        # Articles typically have most relevant content in the middle
        sentences = self.text_processor.split_sentences(text)
        if len(sentences) > 10:
            # Skip first and last 10% (likely headers/footers)
            skip = len(sentences) // 10
            main_content = sentences[skip:-skip] if skip > 0 else sentences
            result["main_content"] = " ".join(main_content)
        else:
            result["main_content"] = text
        
        self.logger.debug(f"Processed article: {result.get('title', 'Unknown')[:50]}...")
        return result


class ProfileProcessor(ContentProcessor):
    """Specialized processor for person/company profiles."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract profile-specific information."""
        result = {
            "content_type": "profile",
            "title": metadata.get("title", ""),
            "text": text,
        }
        
        # Extract structured profile data
        if "og:title" in metadata:
            result["profile_name"] = metadata["og:title"]
        
        if "description" in metadata:
            result["description"] = metadata["description"]
        
        # Profiles are usually concise, use full content
        result["main_content"] = text
        
        self.logger.debug(f"Processed profile: {result.get('profile_name', 'Unknown')[:50]}...")
        return result


class ListingProcessor(ContentProcessor):
    """Specialized processor for search results and directory listings."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract listing-specific information."""
        result = {
            "content_type": "listing",
            "title": metadata.get("title", ""),
            "text": text,
        }
        
        # Listings have many items, extract overview
        # Focus on first occurrence of key terms
        sentences = self.text_processor.split_sentences(text)
        if len(sentences) > 20:
            # Take first 20 sentences as overview
            result["main_content"] = " ".join(sentences[:20])
        else:
            result["main_content"] = text
        
        # Note: Listings often need follow-up crawling
        result["requires_follow_up"] = True
        
        self.logger.debug(f"Processed listing page: {result.get('title', 'Unknown')[:50]}...")
        return result


class ForumProcessor(ContentProcessor):
    """Specialized processor for forum discussions and Q&A pages."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract forum-specific information."""
        result = {
            "content_type": "forum",
            "title": metadata.get("title", ""),
            "text": text,
        }
        
        # Forums have questions and multiple answers
        # Extract the main question/topic
        sentences = self.text_processor.split_sentences(text)
        if len(sentences) > 5:
            # First few sentences usually contain the question
            result["main_content"] = " ".join(sentences[:5])
        else:
            result["main_content"] = text
        
        # Forums are often noisy, mark for careful extraction
        result["high_noise"] = True
        
        self.logger.debug(f"Processed forum thread: {result.get('title', 'Unknown')[:50]}...")
        return result


class ProductProcessor(ContentProcessor):
    """Specialized processor for product pages."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract product-specific information."""
        result = {
            "content_type": "product",
            "title": metadata.get("title", ""),
            "text": text,
        }
        
        # Extract product name
        if "og:title" in metadata:
            result["product_name"] = metadata["og:title"]
        
        # Product pages have descriptions and specs
        result["main_content"] = text
        
        self.logger.debug(f"Processed product page: {result.get('product_name', 'Unknown')[:50]}...")
        return result


class DocumentationProcessor(ContentProcessor):
    """Specialized processor for technical documentation."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract documentation-specific information."""
        result = {
            "content_type": "documentation",
            "title": metadata.get("title", ""),
            "text": text,
        }
        
        # Documentation is structured and technical
        # Use full content
        result["main_content"] = text
        result["is_technical"] = True
        
        self.logger.debug(f"Processed documentation: {result.get('title', 'Unknown')[:50]}...")
        return result


class GenericProcessor(ContentProcessor):
    """Generic processor for unclassified content."""
    
    def process(self, html: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process generic content."""
        result = {
            "content_type": "generic",
            "title": metadata.get("title", ""),
            "text": text,
            "main_content": text,
        }
        
        self.logger.debug("Processed generic content")
        return result


class ContentRouter:
    """
    Routes content to specialized processors based on content type.
    """
    
    def __init__(self, classifier: Optional[ContentTypeClassifier] = None):
        """
        Initialize content router.
        
        Args:
            classifier: ContentTypeClassifier instance (creates new one if not provided)
        """
        self.logger = logging.getLogger(__name__)
        self.classifier = classifier or ContentTypeClassifier()
        
        # Map content types to processors
        self.processors = {
            ContentType.ARTICLE: ArticleProcessor(),
            ContentType.PROFILE: ProfileProcessor(),
            ContentType.LISTING: ListingProcessor(),
            ContentType.FORUM: ForumProcessor(),
            ContentType.PRODUCT: ProductProcessor(),
            ContentType.DOCUMENTATION: DocumentationProcessor(),
            ContentType.GENERIC: GenericProcessor(),
        }
    
    def route_and_process(
        self,
        html: str,
        text: str,
        url: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Classify content type and route to appropriate processor.
        
        Args:
            html: Raw HTML content
            text: Cleaned text content
            url: Page URL
            metadata: Page metadata
            
        Returns:
            Processed content with extraction hints
        """
        # Classify content type
        content_type, confidence = self.classifier.classify(html, url)
        
        # Get appropriate processor
        processor = self.processors.get(content_type, self.processors[ContentType.GENERIC])
        
        # Process content
        result = processor.process(html, text, metadata)
        result["classification_confidence"] = confidence
        result["url"] = url
        
        self.logger.info(
            f"Routed {url} to {content_type.value} processor (confidence: {confidence:.2f})"
        )
        
        return result

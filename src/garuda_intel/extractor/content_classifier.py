"""
Content type classification for automatic routing to specialized processors.
"""

import logging
import re
from enum import Enum
from typing import Tuple, Optional
from urllib.parse import urlparse


class ContentType(Enum):
    """Types of web content for specialized processing."""
    ARTICLE = "article"
    PROFILE = "profile"
    LISTING = "listing"
    FORUM = "forum"
    PRODUCT = "product"
    DOCUMENTATION = "documentation"
    GENERIC = "generic"


class ContentTypeClassifier:
    """
    Classifies web content type based on URL patterns and HTML structure.
    Enables routing to specialized processors for better extraction quality.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # URL pattern matchers for content types
        self.url_patterns = {
            ContentType.ARTICLE: [
                r'/blog/', r'/news/', r'/article/', r'/post/', r'/press/',
                r'/insights/', r'/stories/', r'/publications/',
            ],
            ContentType.PROFILE: [
                r'/profile/', r'/people/', r'/team/', r'/about/', r'/leadership/',
                r'/person/', r'/biography/', r'/bio/', r'/executive/',
            ],
            ContentType.LISTING: [
                r'/search', r'/list', r'/directory', r'/catalog', r'/results',
                r'/companies', r'/organizations', r'/browse',
            ],
            ContentType.FORUM: [
                r'/forum/', r'/discussion/', r'/thread/', r'/topic/', r'/community/',
                r'/question/', r'/answers/',
            ],
            ContentType.PRODUCT: [
                r'/product/', r'/item/', r'/shop/', r'/store/', r'/buy/',
                r'/catalog/', r'/marketplace/',
            ],
            ContentType.DOCUMENTATION: [
                r'/docs/', r'/documentation/', r'/manual/', r'/guide/', r'/api/',
                r'/reference/', r'/wiki/',
            ],
        }
        
        # Domain patterns that indicate specific content types
        self.domain_patterns = {
            ContentType.FORUM: [
                r'stackoverflow', r'reddit', r'quora', r'discourse',
            ],
            ContentType.PROFILE: [
                r'linkedin', r'twitter', r'github', r'facebook',
            ],
            ContentType.DOCUMENTATION: [
                r'docs\.', r'developer\.', r'api\.',
            ],
        }

    def classify(self, html: str, url: str) -> Tuple[ContentType, float]:
        """
        Classify content type based on URL and HTML structure.
        
        Args:
            html: HTML content of the page
            url: URL of the page
            
        Returns:
            Tuple of (ContentType, confidence_score)
        """
        scores = {ct: 0.0 for ct in ContentType}
        
        # URL-based classification
        url_lower = url.lower()
        parsed_url = urlparse(url_lower)
        path = parsed_url.path
        domain = parsed_url.netloc
        
        # Check URL path patterns
        for content_type, patterns in self.url_patterns.items():
            for pattern in patterns:
                if re.search(pattern, path):
                    scores[content_type] += 0.4
        
        # Check domain patterns
        for content_type, patterns in self.domain_patterns.items():
            for pattern in patterns:
                if re.search(pattern, domain):
                    scores[content_type] += 0.5
        
        # HTML structure-based classification
        if html:
            html_lower = html.lower()
            
            # Article indicators
            if any(tag in html_lower for tag in ['<article', 'class="article', 'id="article']):
                scores[ContentType.ARTICLE] += 0.3
            if '<time' in html_lower or 'datetime' in html_lower:
                scores[ContentType.ARTICLE] += 0.2
            if 'author' in html_lower:
                scores[ContentType.ARTICLE] += 0.1
            
            # Profile indicators
            if any(tag in html_lower for tag in ['class="profile', 'id="profile', 'class="bio']):
                scores[ContentType.PROFILE] += 0.3
            if re.search(r'(position|title|role).*:', html_lower):
                scores[ContentType.PROFILE] += 0.2
            
            # Listing indicators
            if html_lower.count('<li') > 10:
                scores[ContentType.LISTING] += 0.2
            if any(tag in html_lower for tag in ['class="search', 'class="results', 'class="listing']):
                scores[ContentType.LISTING] += 0.3
            
            # Forum indicators
            if any(tag in html_lower for tag in ['class="comment', 'class="reply', 'class="thread']):
                scores[ContentType.FORUM] += 0.3
            if html_lower.count('posted by') > 2:
                scores[ContentType.FORUM] += 0.2
            
            # Product indicators
            if any(tag in html_lower for tag in ['class="price', 'add to cart', 'buy now']):
                scores[ContentType.PRODUCT] += 0.3
            if 'itemprop="price"' in html_lower:
                scores[ContentType.PRODUCT] += 0.2
            
            # Documentation indicators
            if any(tag in html_lower for tag in ['class="doc', 'id="documentation', 'class="api']):
                scores[ContentType.DOCUMENTATION] += 0.3
            if html_lower.count('<code>') > 5:
                scores[ContentType.DOCUMENTATION] += 0.2
        
        # Find content type with highest score
        max_score = max(scores.values())
        
        if max_score < 0.3:
            # Low confidence, default to generic
            return ContentType.GENERIC, max_score
        
        # Get content type with highest score
        best_type = max(scores.items(), key=lambda x: x[1])[0]
        confidence = min(max_score, 1.0)
        
        self.logger.debug(
            f"Classified content as {best_type.value} with confidence {confidence:.2f} for URL: {url}"
        )
        
        return best_type, confidence

    def classify_from_url(self, url: str) -> Tuple[ContentType, float]:
        """
        Quick classification based only on URL patterns.
        Useful when HTML is not available.
        
        Args:
            url: URL of the page
            
        Returns:
            Tuple of (ContentType, confidence_score)
        """
        return self.classify("", url)

import re
from typing import List, Tuple, Dict
from urllib.parse import urlparse
from ..types.entity.type import EntityType


class URLScorer:
    # Restored for compatibility with engine/_build_seed_urls logic
    REGISTRY_DOMAINS = {
        "opencorporates.com",
        "northdata.de",
        "company-information.service.gov.uk",
        "crunchbase.com",
        "pitchbook.com",
        "bloomberg.com",
        "reuters.com",
        "dnb.com",
        "linkedin.com",
        "facebook.com",
        "twitter.com",
        "instagram.com",
        "wikipedia.org",
        "zoominfo.com",
        "kompass.com",
        "yellowpages.com",
        "gelbeseiten.de",
        "yelp.com",
        "firmenwissen.de",
    }

    def __init__(self, company_name: str, entity_type: EntityType, patterns: List[Dict] = None, domains: List[Dict] = None):
        self.entity_type = entity_type
        self.company_name = company_name.lower()
        self.company_words = set(self.company_name.split())
        self.company_words -= {"inc", "llc", "ltd", "corp", "corporation", "company", "co", "gmbh", "ag", "limited"}
        self.clean_company_name = re.sub(r"[^a-z0-9]", "", self.company_name)
        self.official_domains = set(d["domain"] for d in (domains or []) if d.get("is_official"))
        self.patterns = patterns or []
        self.domains = domains or []
        self.blacklist_compiled = self._compile_blacklist()
        self.dynamic_domains = {}  # track learned boosts
        
        # Learning system attributes
        self._domain_learning = {}  # domain -> {success_count, fail_count, avg_quality}
        self._pattern_weights = {}  # pattern -> learned weight adjustment

    def boost_domain(self, domain: str, amount: float = 25.0):
        """Allows the explorer to 'learn' which domains are useful."""
        self.dynamic_domains[domain] = self.dynamic_domains.get(domain, 0) + amount

    def _compile_blacklist(self):
        default = [
            r"facebook\.com/sharer",
            r"twitter\.com/intent",
            r"linkedin\.com/share",
            r"mailto:",
            r"sms:",
            r"tel:",
            r"javascript:",
            r"#$",
            r"/rss\.xml",
            r"/feed\.xml",
            r"/privacy",
            r"/terms",
            r"/login",
            r"/signup",
            r"/register",
            r"/newsletter",
        ]
        return [re.compile(p, re.IGNORECASE) for p in default]

    def score_url(self, url: str, link_text: str = "", current_depth: int = 0) -> Tuple[float, str]:
        url_lower = url.lower()
        text_lower = link_text.lower()
        for pattern in self.blacklist_compiled:
            if pattern.search(url_lower):
                return (0.0, "Blacklisted pattern")
        if not url_lower.startswith(("http://", "https://")):
            return (0.0, "Non-HTTP URL")

        score = 40.0  # higher base to avoid zero starts
        reasons = ["Base topic score"]

        # Topic-specific boost
        if self.entity_type == EntityType.TOPIC:
            topic_keywords = ["wiki", "encyclopedia", "journal", "edu", "theory", "science"]
            for kw in topic_keywords:
                if kw in url_lower:
                    score += 30
                    reasons.append(f"Topic-relevant domain: {kw}")

        # Strong name matches
        for word in self.company_words:
            if len(word) > 3 and (word in url_lower or word in text_lower):
                score += 50
                reasons.append(f"Match: {word}")

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        clean_domain = domain.replace("www.", "")
        sld = clean_domain.split(".")[0]
        clean_sld = re.sub(r"[^a-z0-9]", "", sld)

        # Domain boosts from supplied domains/patterns
        for d in self.domains:
            if d["domain"] in domain:
                score += d.get("weight", 0)
                reasons.append(f"Domain pattern: {d['domain']}")
                if d.get("is_official"):
                    self.official_domains.add(d["domain"])
                    score += 150
                    reasons.append("Official domain")
                break

        # Exact company name match in domain
        if self.clean_company_name and clean_sld == self.clean_company_name:
            score += 40
            reasons.append("Exact company name match in domain")

        # Regex patterns
        for p in self.patterns:
            pat = p.get("pattern")
            w = p.get("weight", 0)
            if pat and re.search(pat, url_lower, re.IGNORECASE):
                score += w
                reasons.append(f"Pattern match: {pat}")
                break

        # Entity-type keywords
        keywords = []
        if self.entity_type == EntityType.NEWS:
            keywords = ["news", "headline", "breaking", "latest"]
        elif self.entity_type == EntityType.PERSON:
            keywords = ["bio", "profile", "interview"]
        elif self.entity_type == EntityType.COMPANY:
            keywords = ["investor", "annual report", "leadership", "board", "sec"]
        else:
            keywords = ["about", "article", "story"]

        for kw in keywords:
            if kw in url_lower or kw in text_lower:
                score += 20
                reasons.append(f"Keyword: {kw}")

        # Company/person name in URL/text
        for word in self.company_words:
            if len(word) > 3 and (word in url_lower or word in text_lower):
                score += 15
                reasons.append("Name match")

        # Dynamic boosts
        for dom, boost in self.dynamic_domains.items():
            if dom in domain:
                score += boost
                reasons.append(f"Learned boost: {dom}")
        
        # Apply learned domain boost
        learned_boost = self.get_learned_boost(domain)
        if abs(learned_boost) > 0.1:
            score += learned_boost
            reasons.append(f"Domain learning: {learned_boost:+.1f}")

        # Depth penalty
        score -= current_depth * 5
        score = max(0, min(score, 150))
        return score, "; ".join(reasons) if reasons else "Base score only"

    def should_explore(self, url: str, link_text: str = "", current_depth: int = 0, threshold: float = 25.0) -> bool:
        score, _ = self.score_url(url, link_text, current_depth)
        return score >= threshold

    def set_official_domains(self, domains: List[str]):
        for d in domains:
            self.official_domains.add(d.lower().replace("www.", ""))
    
    def learn_domain_pattern(self, domain: str, success: bool, intel_quality: float) -> None:
        """
        Learn from domain crawl results to adjust future scoring.
        
        Args:
            domain: Domain name that was crawled
            success: Whether the crawl yielded useful intelligence
            intel_quality: Quality score of extracted intelligence (0-1)
        """
        domain = domain.lower().replace("www.", "")
        
        if domain not in self._domain_learning:
            self._domain_learning[domain] = {
                "success_count": 0,
                "fail_count": 0,
                "total_quality": 0.0,
                "crawl_count": 0,
            }
        
        stats = self._domain_learning[domain]
        stats["crawl_count"] += 1
        
        if success:
            stats["success_count"] += 1
            stats["total_quality"] += intel_quality
        else:
            stats["fail_count"] += 1
    
    def get_learned_boost(self, domain: str) -> float:
        """
        Get learned boost factor for a domain.
        
        Args:
            domain: Domain name
            
        Returns:
            Boost score to add to URL score
        """
        domain = domain.lower().replace("www.", "")
        stats = self._domain_learning.get(domain)
        
        if not stats or stats["crawl_count"] < 3:
            # Need at least 3 crawls to learn from
            return 0.0
        
        # Calculate success rate
        success_rate = stats["success_count"] / stats["crawl_count"]
        
        # Calculate average quality
        avg_quality = 0.0
        if stats["success_count"] > 0:
            avg_quality = stats["total_quality"] / stats["success_count"]
        
        # Boost is based on both success rate and quality
        # High success + high quality = strong boost
        # Low success = penalty
        if success_rate >= 0.7:
            boost = avg_quality * 30.0  # Up to +30 for excellent domains
        elif success_rate >= 0.5:
            boost = avg_quality * 15.0  # Up to +15 for good domains
        elif success_rate < 0.3:
            boost = -20.0  # Penalty for unreliable domains
        else:
            boost = 0.0
        
        return boost
    
    def update_pattern_weights(self, patterns: List[Dict]) -> None:
        """
        Update pattern weights based on success metrics.
        
        Args:
            patterns: List of pattern dicts with 'pattern', 'weight', and optionally 'success_count'
        """
        for p in patterns:
            pattern = p.get("pattern")
            if not pattern:
                continue
            
            # Store learned adjustment
            success_count = p.get("success_count", 0)
            total_uses = p.get("total_uses", 1)
            
            if total_uses >= 5:  # Need enough data
                success_rate = success_count / total_uses
                
                # Adjust weight based on success rate
                if success_rate >= 0.8:
                    self._pattern_weights[pattern] = 10.0  # Boost successful patterns
                elif success_rate >= 0.6:
                    self._pattern_weights[pattern] = 5.0
                elif success_rate < 0.3:
                    self._pattern_weights[pattern] = -10.0  # Penalize unsuccessful patterns

import re
from typing import List, Tuple, Dict
from urllib.parse import urlparse
from .models.entities import EntityType


class URLScorer:
    # Restored for compatibility with engine/_build_seed_urls logic
    REGISTRY_DOMAINS = {
        'opencorporates.com',
        'northdata.de',
        'company-information.service.gov.uk',
        'crunchbase.com',
        'pitchbook.com',
        'bloomberg.com',
        'reuters.com',
        'dnb.com',
        'linkedin.com',
        'facebook.com',
        'twitter.com',
        'instagram.com',
        'wikipedia.org',
        'zoominfo.com',
        'kompass.com',
        'yellowpages.com',
        'gelbeseiten.de',
        'yelp.com',
        'firmenwissen.de'
    }

    def __init__(self, company_name: str, entity_type: EntityType, patterns: List[Dict] = None, domains: List[Dict] = None):
        self.entity_type = entity_type
        self.company_name = company_name.lower()
        self.company_words = set(self.company_name.split())
        self.company_words -= {'inc', 'llc', 'ltd', 'corp', 'corporation', 'company', 'co', 'gmbh', 'ag', 'limited'}
        self.clean_company_name = re.sub(r'[^a-z0-9]', '', self.company_name)
        self.official_domains = set(d["domain"] for d in (domains or []) if d.get("is_official"))
        self.patterns = patterns or []
        self.domains = domains or []
        self.blacklist_compiled = self._compile_blacklist()
        self.dynamic_domains = {} # Add this to track learned boosts

    def boost_domain(self, domain: str, amount: float = 25.0):
        """Allows the explorer to 'learn' which domains are useful."""
        self.dynamic_domains[domain] = self.dynamic_domains.get(domain, 0) + amount

    def _compile_blacklist(self):
        default = [
            r'facebook\.com/sharer', r'twitter\.com/intent', r'linkedin\.com/share',
            r'mailto:', r'sms:', r'tel:', r'javascript:', r'#$', r'/rss\.xml', r'/feed\.xml',
            r'/privacy', r'/terms', r'/login', r'/signup', r'/register', r'/newsletter'
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

        score = 40.0  # Increase base score so we don't start at zero
        reasons = ["Base topic score"]
        
        url_lower = url.lower()
        text_lower = link_text.lower()
    
        # Add specific logic for TOPIC type
        if self.entity_type == EntityType.TOPIC:
            topic_keywords = ["wiki", "encyclopedia", "journal", "edu", "theory", "science"]
            for kw in topic_keywords:
                if kw in url_lower:
                    score += 30
                    reasons.append(f"Topic-relevant domain: {kw}")
    
        # Ensure the name match is robust
        for word in self.company_words:
            if len(word) > 3 and (word in url_lower or word in text_lower):
                score += 50 # Give a massive boost for the actual entity name
                reasons.append(f"Match: {word}")

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        clean_domain = domain.replace("www.", "")
        sld = clean_domain.split(".")[0]
        clean_sld = re.sub(r"[^a-z0-9]", "", sld)

        # Domain boosts from data
        for d in self.domains:
            if d["domain"] in domain:
                score += d.get("weight", 0)
                reasons.append(f"Domain pattern: {d['domain']}")
                if d.get("is_official"):
                    self.official_domains.add(d["domain"])
                    score += 150
                    reasons.append("Official domain")
                break

        # Exact name match boost for non-registry
        if self.clean_company_name and clean_sld == self.clean_company_name:
            score += 40
            reasons.append("Exact company name match in domain")

        # Data-driven patterns
        for p in self.patterns:
            pat = p.get("pattern")
            w = p.get("weight", 0)
            if pat and re.search(pat, url_lower, re.IGNORECASE):
                score += w
                reasons.append(f"Pattern match: {pat}")
                break

        # Entity-specific keywords in link text/URL
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

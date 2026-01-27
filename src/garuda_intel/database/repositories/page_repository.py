"""Page and PageContent repository - handles all page-related database operations."""
import logging
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import select, func, or_
from sqlalchemy.orm import sessionmaker, aliased

from ..models import Page, PageContent
from ..helpers import uuid5_url, uuid4, as_dict


class PageRepository:
    """Repository for Page and PageContent operations."""
    
    def __init__(self, session_maker: sessionmaker):
        self.Session = session_maker
        self.logger = logging.getLogger(__name__)
        
    def get_all_pages(
        self,
        q: Optional[str] = None,
        entity_type: Optional[str] = None,
        page_type: Optional[str] = None,
        min_score: Optional[float] = None,
        sort: str = "fresh",
        limit: int = 200,
    ) -> List[Page]:
        """Get all pages matching the given filters."""
        q_norm = (q or "").strip().lower()
        pc = aliased(PageContent, flat=True)
        try:
            with self.Session() as s:
                stmt = select(Page).outerjoin(pc, Page.id == pc.page_id)

                conditions = []
                if q_norm:
                    like = f"%{q_norm}%"
                    conditions.append(
                        or_(
                            func.lower(Page.url).ilike(like),
                            func.lower(Page.page_type).ilike(like),
                            func.lower(Page.entity_type).ilike(like),
                            func.lower(Page.domain_key).ilike(like),
                            func.lower(Page.last_status).ilike(like),
                            func.lower(pc.text).ilike(like),
                        )
                    )
                if entity_type:
                    conditions.append(Page.entity_type == entity_type)
                if page_type:
                    conditions.append(Page.page_type == page_type)
                if min_score is not None:
                    conditions.append(Page.score >= min_score)

                if conditions:
                    stmt = stmt.where(*conditions)

                if sort == "score":
                    stmt = stmt.order_by(Page.score.desc().nullslast(), Page.last_fetch_at.desc().nullslast())
                else:
                    stmt = stmt.order_by(Page.last_fetch_at.desc().nullslast())

                stmt = stmt.limit(limit)
                results = s.execute(stmt).scalars().all()
                return results or []
        except Exception as e:
            self.logger.error(f"get_all_pages failed: {e}")
            return []

    def get_page_by_url(self, url: str) -> Optional[Dict]:
        """Get page metadata by URL."""
        with self.Session() as s:
            p = s.execute(select(Page).where(Page.url == url)).scalar_one_or_none()
            if not p:
                return None
            return p.to_dict()

    def get_page_content_by_url(self, url: str) -> Optional[Dict]:
        """Get page content (HTML, text, metadata) by URL."""
        with self.Session() as s:
            page_id = s.execute(select(Page.id).where(Page.url == url)).scalar_one_or_none()
            if not page_id:
                return None
            pc = s.execute(select(PageContent).where(PageContent.page_id == page_id)).scalar_one_or_none()
            if pc:
                return {
                    "html": pc.html,
                    "text": pc.text,
                    "metadata": as_dict(pc.metadata_json),
                    "extracted": as_dict(pc.extracted_json),
                    "fetch_ts": pc.fetch_ts.isoformat(),
                }
            return None

    def save_page(self, page: Dict) -> str:
        """
        Upsert page + content. Returns the page UUID.
        If no id is provided, a deterministic UUID5 is derived from the URL.
        """
        url = page.get("url")
        if not url:
            raise ValueError("page url is required")
        page_id = page.get("id") or uuid5_url(url)

        with self.Session() as s:
            p = Page(
                id=page_id,
                url=url,
                entity_type=page.get("entity_type"),
                domain_key=page.get("domain_key"),
                depth=page.get("depth"),
                score=page.get("score"),
                page_type=page.get("page_type"),
                last_status=page.get("last_status"),
                last_fetch_at=page.get("last_fetch_at"),
                text_length=page.get("text_length"),
            )
            pc = PageContent(
                id=uuid4(),
                page_id=page_id,
                html=page.get("html", ""),
                text=page.get("text_content", ""),
                metadata_json=page.get("metadata", {}) or {},
                extracted_json=page.get("extracted", {}) or {},
                fetch_ts=page.get("last_fetch_at") or datetime.utcnow(),
            )
            s.merge(p)
            s.merge(pc)
            s.commit()
            return page_id

    def mark_visited(self, url: str):
        """Mark a page as visited."""
        with self.Session() as s:
            p = s.execute(select(Page).where(Page.url == url)).scalar_one_or_none()
            if p:
                p.last_status = "visited"
                p.last_fetch_at = datetime.utcnow()
                s.commit()

    def has_visited(self, url: str) -> bool:
        """Check if a page has been visited."""
        with self.Session() as s:
            return s.execute(select(Page.id).where(Page.url == url)).scalar_one_or_none() is not None

    def resolve_page_id(self, session, url: Optional[str]) -> Optional[str]:
        """Internal helper to get page ID from URL within an existing session."""
        if not url:
            return None
        return session.execute(select(Page.id).where(Page.url == url)).scalar_one_or_none()

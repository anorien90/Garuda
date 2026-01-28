"""Media-entity linking service for searchable media intelligence.

This module links extracted media content to entities, making media
text searchable and traceable in the knowledge graph.
"""

from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import uuid
import re


class MediaEntityLinker:
    """Links media content to entities for searchable intelligence.
    
    Features:
    - Extract entity mentions from media text
    - Create media-entity relationships
    - Track media as intelligence sources
    - Enable media content search
    - Maintain provenance chain
    
    The linker makes media content first-class intelligence by:
    1. Extracting text from media (OCR, transcription, etc.)
    2. Identifying entity mentions in the text
    3. Creating bidirectional links
    4. Storing media as searchable content
    """
    
    def __init__(self, db_session):
        """Initialize media-entity linker.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
    
    def link_media_to_entities(
        self,
        media_url: str,
        media_type: str,
        extracted_text: str,
        page_id: Optional[str] = None,
        processing_method: Optional[str] = None,
        confidence: float = 0.8
    ) -> str:
        """Link media content to mentioned entities.
        
        Args:
            media_url: URL of media file
            media_type: Type of media (image, video, audio, pdf)
            extracted_text: Text extracted from media
            page_id: Optional source page ID
            processing_method: How text was extracted (ocr, transcription, etc.)
            confidence: Extraction confidence (0.0-1.0)
            
        Returns:
            ID of created MediaContent record
        """
        from ..database.models import MediaContent, Entity
        
        # Find entity mentions in text
        mentioned_entities = self._find_entity_mentions(extracted_text)
        
        # Create MediaContent record
        media_content = MediaContent(
            id=uuid.uuid4(),
            media_url=media_url,
            media_type=media_type,
            extracted_text=extracted_text,
            page_id=uuid.UUID(page_id) if page_id else None,
            entities_mentioned=mentioned_entities,
            processing_method=processing_method,
            confidence=confidence,
            metadata_json={
                "text_length": len(extracted_text),
                "entity_count": len(mentioned_entities.get("entities", [])),
                "linked_at": datetime.utcnow().isoformat()
            }
        )
        
        self.db.add(media_content)
        self.db.commit()
        
        # Create relationships from media to entities
        self._create_media_entity_relationships(
            str(media_content.id),
            mentioned_entities
        )
        
        return str(media_content.id)
    
    def _find_entity_mentions(self, text: str) -> Dict[str, Any]:
        """Find entity mentions in media text.
        
        Args:
            text: Extracted media text
            
        Returns:
            Dict with entity IDs and mention details
        """
        from ..database.models import Entity
        
        # Get all entities from database
        entities = self.db.query(Entity).all()
        
        mentions = {
            "entities": [],
            "mention_counts": {}
        }
        
        text_lower = text.lower()
        
        for entity in entities:
            # Check for entity name in text
            entity_name = entity.name.lower()
            
            # Simple substring match (can be enhanced with NER)
            if entity_name in text_lower:
                entity_id = str(entity.id)
                
                # Count mentions
                count = text_lower.count(entity_name)
                
                mentions["entities"].append({
                    "entity_id": entity_id,
                    "entity_name": entity.name,
                    "entity_type": entity.kind,
                    "mention_count": count
                })
                
                mentions["mention_counts"][entity_id] = count
        
        return mentions
    
    def _create_media_entity_relationships(
        self,
        media_content_id: str,
        mentioned_entities: Dict[str, Any]
    ):
        """Create relationships between media and entities.
        
        Args:
            media_content_id: MediaContent record ID
            mentioned_entities: Dict with entity mentions
        """
        from ..database.models import Relationship
        
        for mention in mentioned_entities.get("entities", []):
            entity_id = mention["entity_id"]
            
            # Create relationship: MediaContent --mentions--> Entity
            relationship = Relationship(
                id=uuid.uuid4(),
                source_id=uuid.UUID(media_content_id),
                target_id=uuid.UUID(entity_id),
                relation_type="mentions",
                source_type="media_content",
                target_type="entity",
                metadata_json={
                    "mention_count": mention["mention_count"],
                    "linked_at": datetime.utcnow().isoformat()
                }
            )
            
            self.db.add(relationship)
        
        self.db.commit()
    
    def get_media_for_entity(
        self,
        entity_id: str,
        media_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all media mentioning an entity.
        
        Args:
            entity_id: Entity ID
            media_type: Optional filter by media type
            
        Returns:
            List of media content dicts
        """
        from ..database.models import MediaContent, Relationship
        
        # Find relationships where entity is target
        query = self.db.query(MediaContent).join(
            Relationship,
            Relationship.source_id == MediaContent.id
        ).filter(
            Relationship.target_id == uuid.UUID(entity_id),
            Relationship.relation_type == "mentions"
        )
        
        if media_type:
            query = query.filter(MediaContent.media_type == media_type)
        
        media_items = query.all()
        
        return [
            {
                "id": str(m.id),
                "media_url": m.media_url,
                "media_type": m.media_type,
                "extracted_text": m.extracted_text[:200] + "..." if len(m.extracted_text or "") > 200 else m.extracted_text,
                "processing_method": m.processing_method,
                "confidence": m.confidence,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in media_items
        ]
    
    def get_entities_in_media(
        self,
        media_content_id: str
    ) -> List[Dict[str, Any]]:
        """Get all entities mentioned in media.
        
        Args:
            media_content_id: MediaContent ID
            
        Returns:
            List of entity dicts
        """
        from ..database.models import Entity, Relationship
        
        # Find entities linked to this media
        entities = self.db.query(Entity).join(
            Relationship,
            Relationship.target_id == Entity.id
        ).filter(
            Relationship.source_id == uuid.UUID(media_content_id),
            Relationship.relation_type == "mentions"
        ).all()
        
        return [
            {
                "id": str(e.id),
                "name": e.name,
                "kind": e.kind,
                "data": e.data
            }
            for e in entities
        ]
    
    def search_media_content(
        self,
        query: str,
        media_type: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Search media content by text query.
        
        Args:
            query: Search query
            media_type: Optional filter by media type
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of matching media content
        """
        from ..database.models import MediaContent
        from sqlalchemy import or_, and_
        
        # Build query
        filters = [MediaContent.confidence >= min_confidence]
        
        if media_type:
            filters.append(MediaContent.media_type == media_type)
        
        # Search in extracted text
        if query:
            query_filter = MediaContent.extracted_text.ilike(f"%{query}%")
            filters.append(query_filter)
        
        media_items = self.db.query(MediaContent).filter(and_(*filters)).all()
        
        return [
            {
                "id": str(m.id),
                "media_url": m.media_url,
                "media_type": m.media_type,
                "extracted_text": m.extracted_text,
                "page_id": str(m.page_id) if m.page_id else None,
                "confidence": m.confidence,
                "entities_mentioned": m.entities_mentioned,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in media_items
        ]
    
    def update_entity_links(self, media_content_id: str):
        """Re-scan media content and update entity links.
        
        Useful when new entities are added to the database.
        
        Args:
            media_content_id: MediaContent ID to update
        """
        from ..database.models import MediaContent, Relationship
        
        # Get media content
        media = self.db.query(MediaContent).filter(
            MediaContent.id == uuid.UUID(media_content_id)
        ).first()
        
        if not media or not media.extracted_text:
            return
        
        # Delete existing relationships
        self.db.query(Relationship).filter(
            Relationship.source_id == uuid.UUID(media_content_id),
            Relationship.relation_type == "mentions"
        ).delete()
        
        # Re-find entity mentions
        mentioned_entities = self._find_entity_mentions(media.extracted_text)
        
        # Update media content record
        media.entities_mentioned = mentioned_entities
        
        # Recreate relationships
        self._create_media_entity_relationships(
            media_content_id,
            mentioned_entities
        )
        
        self.db.commit()

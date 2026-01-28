"""Tests for media-entity linking."""

import pytest
from unittest.mock import Mock, MagicMock, patch
import uuid

from garuda_intel.services.media_linker import MediaEntityLinker


class TestMediaEntityLinker:
    """Tests for MediaEntityLinker service."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query.return_value = session
        session.filter.return_value = session
        session.join.return_value = session
        session.all.return_value = []
        session.first.return_value = None
        return session
    
    @pytest.fixture
    def linker(self, mock_db_session):
        """Create MediaEntityLinker instance."""
        return MediaEntityLinker(mock_db_session)
    
    def test_initialization(self, mock_db_session):
        """Test linker initialization."""
        linker = MediaEntityLinker(mock_db_session)
        assert linker.db == mock_db_session
    
    def test_find_entity_mentions_basic(self, linker, mock_db_session):
        """Test finding entity mentions in text."""
        # Create mock entities
        entity1 = Mock()
        entity1.id = uuid.uuid4()
        entity1.name = "John Doe"
        entity1.kind = "person"
        
        entity2 = Mock()
        entity2.id = uuid.uuid4()
        entity2.name = "Acme Corp"
        entity2.kind = "company"
        
        mock_db_session.query.return_value.all.return_value = [entity1, entity2]
        
        text = "John Doe works at Acme Corp in San Francisco."
        
        mentions = linker._find_entity_mentions(text)
        
        assert "entities" in mentions
        assert "mention_counts" in mentions
        assert len(mentions["entities"]) == 2
        
        # Check both entities were found
        entity_names = [e["entity_name"] for e in mentions["entities"]]
        assert "John Doe" in entity_names
        assert "Acme Corp" in entity_names
    
    def test_find_entity_mentions_multiple_occurrences(self, linker, mock_db_session):
        """Test counting multiple mentions of same entity."""
        entity = Mock()
        entity.id = uuid.uuid4()
        entity.name = "TechCorp"
        entity.kind = "company"
        
        mock_db_session.query.return_value.all.return_value = [entity]
        
        text = "TechCorp announced today. TechCorp's CEO said TechCorp will expand."
        
        mentions = linker._find_entity_mentions(text)
        
        assert len(mentions["entities"]) == 1
        assert mentions["entities"][0]["mention_count"] == 3
    
    def test_find_entity_mentions_no_matches(self, linker, mock_db_session):
        """Test when no entities are mentioned."""
        entity = Mock()
        entity.id = uuid.uuid4()
        entity.name = "Acme Corp"
        entity.kind = "company"
        
        mock_db_session.query.return_value.all.return_value = [entity]
        
        text = "This text contains no entity mentions."
        
        mentions = linker._find_entity_mentions(text)
        
        assert len(mentions["entities"]) == 0
    
    @patch('garuda_intel.services.media_linker.uuid.uuid4')
    def test_link_media_to_entities(self, mock_uuid, linker, mock_db_session):
        """Test linking media to entities."""
        # Setup
        mock_media_id = uuid.uuid4()
        mock_uuid.return_value = mock_media_id
        
        entity = Mock()
        entity.id = uuid.uuid4()
        entity.name = "Tesla"
        entity.kind = "company"
        
        mock_db_session.query.return_value.all.return_value = [entity]
        
        # Patch _create_media_entity_relationships to avoid UUID conversion issue
        with patch.object(linker, '_create_media_entity_relationships'):
            # Link media
            media_id = linker.link_media_to_entities(
                media_url="http://example.com/image.jpg",
                media_type="image",
                extracted_text="Tesla announced new features today.",
                page_id=None,
                processing_method="ocr",
                confidence=0.9
            )
            
            assert media_id == str(mock_media_id)
            mock_db_session.add.assert_called()
            mock_db_session.commit.assert_called()
    
    def test_create_media_entity_relationships(self, linker, mock_db_session):
        """Test creating relationships between media and entities."""
        media_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        
        mentioned_entities = {
            "entities": [
                {
                    "entity_id": entity_id,
                    "entity_name": "Test Entity",
                    "entity_type": "company",
                    "mention_count": 2
                }
            ]
        }
        
        linker._create_media_entity_relationships(media_id, mentioned_entities)
        
        # Verify relationship was added
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()
    
    def test_get_media_for_entity(self, linker, mock_db_session):
        """Test getting all media mentioning an entity."""
        # Create mock media content
        media1 = Mock()
        media1.id = uuid.uuid4()
        media1.media_url = "http://example.com/image1.jpg"
        media1.media_type = "image"
        media1.extracted_text = "Entity mentioned here"
        media1.processing_method = "ocr"
        media1.confidence = 0.9
        media1.created_at = Mock()
        media1.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        
        mock_db_session.query.return_value.join.return_value.filter.return_value.all.return_value = [media1]
        
        entity_id = str(uuid.uuid4())
        results = linker.get_media_for_entity(entity_id)
        
        assert len(results) == 1
        assert results[0]["media_url"] == "http://example.com/image1.jpg"
        assert results[0]["media_type"] == "image"
    
    def test_get_media_for_entity_filtered_by_type(self, linker, mock_db_session):
        """Test getting media filtered by type."""
        entity_id = str(uuid.uuid4())
        
        # Call with media type filter
        linker.get_media_for_entity(entity_id, media_type="video")
        
        # Verify filter was applied
        mock_db_session.query.assert_called()
    
    def test_get_entities_in_media(self, linker, mock_db_session):
        """Test getting all entities mentioned in media."""
        # Create mock entities
        entity1 = Mock()
        entity1.id = uuid.uuid4()
        entity1.name = "Entity 1"
        entity1.kind = "person"
        entity1.data = {"field": "value"}
        
        mock_db_session.query.return_value.join.return_value.filter.return_value.all.return_value = [entity1]
        
        media_id = str(uuid.uuid4())
        results = linker.get_entities_in_media(media_id)
        
        assert len(results) == 1
        assert results[0]["name"] == "Entity 1"
        assert results[0]["kind"] == "person"
    
    def test_search_media_content(self, linker, mock_db_session):
        """Test searching media content by query."""
        # Create mock media
        media1 = Mock()
        media1.id = uuid.uuid4()
        media1.media_url = "http://example.com/doc.pdf"
        media1.media_type = "pdf"
        media1.extracted_text = "This document discusses machine learning"
        media1.page_id = None
        media1.confidence = 0.85
        media1.entities_mentioned = {"entities": []}
        media1.created_at = Mock()
        media1.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [media1]
        
        results = linker.search_media_content("machine learning")
        
        assert len(results) == 1
        assert "machine learning" in results[0]["extracted_text"]
    
    def test_search_media_content_with_type_filter(self, linker, mock_db_session):
        """Test searching with media type filter."""
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        linker.search_media_content("query", media_type="video")
        
        # Verify query was called
        mock_db_session.query.assert_called()
    
    def test_search_media_content_with_confidence_filter(self, linker, mock_db_session):
        """Test searching with confidence threshold."""
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        linker.search_media_content("query", min_confidence=0.8)
        
        # Verify query was called
        mock_db_session.query.assert_called()
    
    def test_update_entity_links(self, linker, mock_db_session):
        """Test updating entity links for media."""
        # Create mock media content
        media = Mock()
        media.id = uuid.uuid4()
        media.extracted_text = "Tesla and SpaceX are companies"
        
        mock_db_session.query.return_value.filter.return_value.first.return_value = media
        
        # Create mock entities
        entity1 = Mock()
        entity1.id = uuid.uuid4()
        entity1.name = "Tesla"
        entity1.kind = "company"
        
        entity2 = Mock()
        entity2.id = uuid.uuid4()
        entity2.name = "SpaceX"
        entity2.kind = "company"
        
        # First call returns existing media, second returns entities
        mock_db_session.query.return_value.all.return_value = [entity1, entity2]
        
        media_id = str(media.id)
        linker.update_entity_links(media_id)
        
        # Verify relationships were recreated
        assert mock_db_session.commit.called
    
    def test_update_entity_links_no_media(self, linker, mock_db_session):
        """Test update with non-existent media."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Should not raise error
        linker.update_entity_links(str(uuid.uuid4()))
    
    def test_update_entity_links_no_text(self, linker, mock_db_session):
        """Test update with media that has no extracted text."""
        media = Mock()
        media.id = uuid.uuid4()
        media.extracted_text = None
        
        mock_db_session.query.return_value.filter.return_value.first.return_value = media
        
        # Should not raise error
        linker.update_entity_links(str(media.id))

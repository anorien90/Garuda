# Garuda Intel Web UI Architecture (Post-Refactoring)

## Component Hierarchy

```
base.html (Main Layout)
├── Header (Logo, Status Indicators, Theme Toggle)
├── Floating Chat Popup (#popup-chat-container)
│   └── chat.html (Minimal form with unique IDs: popup-chat-*)
└── Main Content Area
    └── index.html (Tab Navigation + Panels)
        ├── Overview (Status Dashboard)
        ├── 🔍 Search (UNIFIED)
        │   └── search-unified.html
        │       ├── SQL Mode
        │       ├── Semantic Mode
        │       ├── RAG Mode (Advanced Multidimensional)
        │       ├── AI Chat Mode (search-tab-chat-*)
        │       └── Entity Search Mode
        ├── 🤖 Agent
        │   └── agent-panel.html
        │       ├── Reflect & Refine
        │       ├── Explore Graph
        │       ├── Autonomous Mode
        │       └── Task Queue
        ├── 🌐 Crawler
        ├── 📄 Data (Pages + Recorder Search)
        ├── 🕸️ Graph (Entity Graph Visualization)
        ├── ✨ Quality
        │   └── data-quality.html
        │       ├── Entity Deduplication (3 tools)
        │       ├── Entity Gap Analysis
        │       ├── Relationship Management
        │       ├── Relationship Confidence
        │       └── Crawl Learning Stats
        ├── 🎬 Media
        ├── 📡 Recorder
        └── ⚙️ Settings
```

## Search Modes Unified

```
┌─────────────────────────────────────────────────────────┐
│                  🔍 Unified Search                      │
├─────────────────────────────────────────────────────────┤
│ Mode Buttons: [SQL] [Semantic] [RAG] [AI Chat] [Entity]│
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │          Mode-Specific Form Fields              │    │
│  │  (Changes based on selected mode)               │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │           Mode-Specific Results                 │    │
│  │  (Each mode has unique container)               │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘

SQL Mode:         Keyword/entity search with confidence filtering
Semantic Mode:    Vector similarity search (embedding-based)
RAG Mode:         Embedding + Graph traversal (multidimensional)
AI Chat Mode:     Deep RAG with autonomous web crawling
Entity Mode:      Hybrid SQL + semantic entity search
```

## Duplicate ID Resolution

### Before (BROKEN):
```
base.html
  └── #chat-container
      └── chat.html (#chat-form, #chat-q, #chat-answer)

index.html
  └── Search Tab
      └── chat.html (#chat-form, #chat-q, #chat-answer)  ❌ DUPLICATES!
```

### After (FIXED):
```
base.html
  └── #popup-chat-container
      └── chat.html (#popup-chat-form, #popup-chat-q, #popup-chat-answer)

index.html
  └── Search Tab
      └── search-unified.html
          └── AI Chat Mode (#search-tab-chat-form, #search-tab-chat-q, #search-tab-chat-answer)
```

## JavaScript Event Handling

```javascript
// Smart form detection in actions/chat.js
chatAsk(event) {
  const formId = event.target.id;
  
  if (formId === 'popup-chat-form') {
    // Use popup-specific IDs
    answerEl = getElementById('popup-chat-answer');
    qEl = getElementById('popup-chat-q');
    // ...
  } else if (formId === 'search-tab-chat-form') {
    // Use search-tab-specific IDs
    answerEl = getElementById('search-tab-chat-answer');
    qEl = getElementById('search-tab-chat-q');
    // ...
  } else {
    // Minimal fallback with warning
  }
}
```

## Quality Tab Organization

```
✨ Quality Tab (data-quality.html)
├── 🔗 Entity Deduplication
│   ├── Find Semantic Duplicates
│   ├── Scan Database for Duplicates
│   └── Find Similar Entities
├── 🎯 Entity Gap Analysis
│   ├── Analyze Gaps (by ID)
│   └── Analyze All (Top 20)
├── 🔄 Relationship Management
│   ├── Validate Relationships
│   ├── Deduplicate Relationships
│   └── Infer Relationships
├── 📊 Relationship Confidence
│   ├── View Statistics
│   ├── High Confidence Relationships
│   └── Record New Relationship
└── 📊 Crawl Learning Stats
    └── Domain Reliability Metrics
```

## Removed Components

### Legacy Tab Panels (from index.html):
- ❌ `data-tab-panel="intel"` (replaced by unified search SQL mode)
- ❌ `data-tab-panel="semantic"` (replaced by unified search Semantic mode)
- ❌ `data-tab-panel="pages"` (merged into Data tab)
- ❌ `data-tab-panel="entity-tools"` (merged into Quality tab)

### Redundant Agent Sub-Tab (from agent-panel.html):
- ❌ "🔍 Multidimensional Search" (now RAG mode in unified search)

### Redundant Quality Sections (from data-quality.html):
- ❌ Semantic Entity Search (now Entity mode in unified search)
- ❌ Entity Path Finding (accessible from Graph tab)
- ❌ Entity-Aware Crawling (belongs in Crawler tab)

## Benefits

1. **Unified Experience**: All search modes in one place with consistent UI
2. **No Duplicate IDs**: Unique identifiers prevent JavaScript conflicts
3. **Better Organization**: Related features grouped logically
4. **Cleaner Code**: Removed redundancy and legacy artifacts
5. **Maintainability**: Easier to understand and modify
6. **Preserved Functionality**: All features still accessible

## File Count

- Modified: 9 files
- Created (backup): 2 files
- New documentation: 2 files
- Total lines changed: ~800 additions, ~300 deletions

# Chat UI Visual Changes

## Before vs After

### Chat Form - Before
```html
<form id="chat-form">
  <textarea id="chat-q">Question</textarea>
  <input id="chat-entity" type="text">Entity (optional)</input>
  <input id="chat-topk" type="number" value="6">Top K</input>
  <button type="submit">🧠 Ask</button>
</form>
```

### Chat Form - After
```html
<div class="4-phase-info-box">
  🔄 4-Phase Intelligent Search Pipeline
  Phase 1: Initial RAG Search
  Phase 2: Retry with Paraphrasing
  Phase 3: Web Crawling
  Phase 4: Re-query RAG
</div>

<form id="chat-form">
  <textarea id="chat-q">Question</textarea>
  <input id="chat-entity">Entity (optional)</input>
  <input id="chat-topk" value="6">Top K</input>
  <input id="chat-max-cycles" value="3">Max Search Cycles (1-10)</input> ⬅️ NEW
  <checkbox id="chat-autonomous-mode">🤖 Autonomous Mode</checkbox> ⬅️ NEW
  <button type="submit">🧠 Ask</button>
</form>
```

### Loading State - Before
```
[Spinning animation]
Thinking (will search online if needed)...
```

### Loading State - After
```
[Spinning animation]
Phase 1: RAG Search...
Searching through embeddings, graph, and SQL data

[If retry triggered]
Phase 2: Paraphrasing...
Retrying with alternative queries

[If crawling triggered]
Phase 3: Web Crawling (2/3 cycles)...
Discovering and indexing online sources
```

### Results Display - Before
```
[Answer text]

Sources & Context (5 total)
- Context 1
- Context 2
...
```

### Results Display - After
```
🧠 RAG: 3 semantic hits  🕸️ Graph: 2 relation hits  📊 SQL: 1 keyword hits
🔄 Search Cycles: 2/3  🔄 Retry with paraphrasing  🌐 Live Crawl: Insufficient high-quality RAG results

[If paraphrased queries used] ⬅️ NEW
🔄 Paraphrased Queries
- "What is Flask used for?"
- "Flask framework applications"
- "Flask Python web development"

[Answer text]

[If URLs crawled] ⬅️ NEW
Live URLs Crawled
- https://flask.palletsprojects.com
- https://github.com/pallets/flask

Sources & Context (5 total)
- [🧠 RAG] Context 1
- [🕸️ Graph] Context 2
- [📊 SQL] Context 3
...

[If autonomous mode enabled] ⬅️ NEW
🤖 Autonomous Discovery Results
🔴 2 Dead Ends  ❓ 3 Knowledge Gaps  📋 2 Plans  ✅ 1 Crawls

🔴 Dead Ends (2)
- Flask (Organization) - Priority: 0.85
- Pallets (Organization) - Priority: 0.72

❓ Knowledge Gaps (3)
- Flask - Missing field: revenue
- Pallets - Missing relationship: parent_company
- Flask - Missing field: headquarters

📋 Crawl Plans (2)
- Flask (3 URLs): https://flask.com/about, ...
- Pallets (2 URLs): https://palletsprojects.com, ...
```

### Error Display - Before
```
[If no answer generated]
No answer generated.
```

### Error Display - After (Always-Answer Guarantee)
```
[Scenario 1: Answer from context snippets]
Based on the available information:

Flask is a lightweight WSGI web application framework...

Pallets is the organization that maintains Flask...

[Scenario 2: No context available]
I searched through local data and online sources but couldn't find 
a definitive answer. Try refining your question or providing more context.

[Scenario 3: No data at all]
No relevant information was found in local data or online sources. 
Try a different question or crawl some relevant pages first.
```

## UI Layout Changes

### Input Grid Layout
```
Before:
┌─────────────────────┬─────────────────────┐
│ Entity (optional)   │ Top K               │
└─────────────────────┴─────────────────────┘

After:
┌─────────────────────┬─────────────────────┐
│ Entity (optional)   │ Top K               │
├─────────────────────┼─────────────────────┤
│ Max Search Cycles   │ [✓] Autonomous Mode │
└─────────────────────┴─────────────────────┘
```

### Color Coding
- **Purple** 🟣 - RAG/Semantic results
- **Teal** 🟢 - Graph results
- **Blue** 🔵 - SQL results
- **Amber** 🟠 - Retry/Paraphrasing
- **Green** 🟢 - Live Crawl
- **Indigo** 🟣 - Autonomous Mode

## User Interaction Flow

### Simple Query Flow
```
1. User types question
2. Click "Ask"
3. See "Phase 1: RAG Search..."
4. [2 seconds]
5. Answer appears with source badges
```

### Complex Query Flow (with autonomous mode)
```
1. User types question
2. Set Max Search Cycles to 5
3. Enable Autonomous Mode checkbox
4. Click "Ask"
5. See "Phase 1: RAG Search..."
6. [3 seconds] - Insufficient results
7. See "Phase 2: Paraphrasing..."
8. Shows paraphrased queries
9. [4 seconds] - Still insufficient
10. See "Phase 3: Web Crawling (1/5 cycles)..."
11. [8 seconds per cycle]
12. Answer appears with:
    - Paraphrased queries section
    - Live URLs crawled
    - Search cycle progress (3/5)
13. See "🤖 Autonomous Mode: Discovering knowledge gaps..."
14. [5 seconds]
15. Autonomous results appear:
    - Dead ends discovered
    - Knowledge gaps identified
    - Crawl plans generated
```

## Accessibility Features

### Semantic HTML
- Proper label/input associations
- ARIA attributes for checkboxes
- Meaningful button text
- Descriptive placeholders

### Visual Feedback
- Loading states with animations
- Color-coded result sources
- Progress indicators (X/Y cycles)
- Collapsible sections for details

### Error Handling
- Always-present feedback
- Clear error messages
- Graceful degradation
- No silent failures

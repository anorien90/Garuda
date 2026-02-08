# Visual Changes - Autonomous Mode Implementation

## Web UI - Agent Control Panel

### Before
The Autonomous Mode tab had:
- Single form with toggle for "Enable Autonomous Crawling"
- Fixed parameters (max entities, priority threshold, depth, max pages)
- Single "Run Autonomous Discovery" button
- Results showed dead-ends, knowledge gaps, and crawl plans

### After
The Autonomous Mode tab now has:

#### 1. Action Selection Cards (4 visual cards)
```
┌────────────────┬────────────────┬────────────────┬────────────────┐
│   🔍 Reflect   │  🕸️ Investigate │   🔄 Combined  │  🤖 Classic    │
│   & Relate     │     Crawl      │      Mode      │   Discovery    │
│                │                │                │                │
│ Find indirect  │ Execute crawls │ Run both in    │ Find dead-ends │
│ connections &  │ based on tasks │ sequence       │ & gaps         │
│ create tasks   │                │                │                │
└────────────────┴────────────────┴────────────────┴────────────────┘
```

#### 2. Dynamic Configuration Panel
Shows/hides options based on selected action:
- **Common**: Max Entities, Priority Threshold, Max Depth, Max Pages
- **Reflect & Relate specific**: Target Entities, Top N Relations
- **Classic Discovery specific**: Auto-crawl toggle

#### 3. Process Monitor Panel
```
┌─ ⚙️ Running Processes ─────────────────────────── [Refresh] ┐
│                                                              │
│  reflect_relate                              🟢 Running     │
│  ID: reflect_relate_1_20240101_120000                       │
│  Current: Analyzing entity graph                            │
│  Progress: 5/10                                  [Stop]     │
│                                                              │
│  investigate_crawl                           ✅ Completed   │
│  ID: investigate_crawl_2_20240101_120530                    │
│  Progress: 10/10                                            │
└──────────────────────────────────────────────────────────────┘
```
- Auto-refreshes every 5 seconds
- Shows status badges (🟢 Running, 🟡 Stopping, ✅ Completed, ❌ Failed)
- Progress tracking for running processes
- Stop button for active processes

#### 4. Results Panel - Mode-Specific Rendering

**Reflect & Relate Results:**
```
Statistics:
┌─────────────────┬──────────────────────┬──────────────────────┐
│ Entities        │ Potential Relations  │ Investigation Tasks  │
│ Analyzed: 50    │ Found: 12           │ Created: 25          │
└─────────────────┴──────────────────────┴──────────────────────┘

🔗 Potential Relations:
• Apple Inc. ↔ Microsoft Corp [Confidence: 0.85]
  Reason: Share 3 common connection(s)
• ...

📋 Investigation Tasks:
• [investigate_relation] Apple Inc. (Priority: 0.85)
  Related to: Microsoft Corp
  Reason: Share 3 common connection(s)
• ...
```

**Investigate Crawl Results:**
```
Statistics:
┌──────────┬───────────┬───────────┬──────────┬────────────┐
│ Tasks    │ Tasks     │ Plans     │ Crawls   │ Pages      │
│ Received │ Processed │ Generated │ Executed │ Discovered │
│ 25       │ 10        │ 10        │ 8        │ 142        │
└──────────┴───────────┴───────────┴──────────┴────────────┘

📋 Generated Crawl Plans:
• Apple Inc. (Priority: 0.850)
  Mode: investigate_relation | Strategy: broad_search
  Queries: Apple Microsoft partnership, ...
• ...

✅ Crawl Results:
• ✓ Apple Inc.: 18 pages crawled
• ✓ Microsoft Corp: 15 pages crawled
• ...
```

**Combined Mode Results:**
```
Overall Statistics:
┌─────────────────────┬────────────────┬───────────────────┐
│ Total Entities      │ Total Crawls   │ Total Pages       │
│ Analyzed: 50        │ Executed: 8    │ Discovered: 142   │
└─────────────────────┴────────────────┴───────────────────┘

Phase 1: Reflect & Relate
  Entities analyzed: 50
  Potential relations: 12
  Investigation tasks: 25

Phase 2: Investigate Crawl
  Tasks processed: 10
  Crawls executed: 8
  Pages discovered: 142
```

## CLI - New Options

### Before
```bash
garuda-agent autonomous --max-entities 10 --priority-threshold 0.3 \
  --depth 3 --auto-crawl --max-pages 25
```

### After
```bash
# New --action flag with 4 modes:
garuda-agent autonomous --action reflect-relate \
  --target-entities "Apple,Microsoft" --top-n 20 --max-depth 2

garuda-agent autonomous --action investigate-crawl \
  --max-entities 10 --max-pages 25 --priority-threshold 0.3

garuda-agent autonomous --action combined \
  --target-entities "Apple" --max-entities 5 --max-pages 25

garuda-agent autonomous --action discover \
  --max-entities 10 --auto-crawl --max-pages 25  # Classic mode (default)
```

### Output Format Examples

**Reflect & Relate Output:**
```
============================================================
AUTONOMOUS MODE REPORT: REFLECT-RELATE
============================================================

Entities analyzed: 50
Potential relations found: 12
Investigation tasks created: 25

--- Potential Relations (12) ---

  Apple Inc. ↔ Microsoft Corp
    Confidence: 0.85 | Share 3 common connection(s)

  Tesla Inc. ↔ SpaceX
    Confidence: 0.75 | Share 2 common connection(s)

--- Investigation Tasks (25) ---

  [investigate_relation] Apple Inc.
    Related to: Microsoft Corp
    Reason: Share 3 common connection(s)
    Priority: 0.85

  [fill_gap] Tesla Inc.
    Reason: Missing kind
    Priority: 0.60
```

## API Endpoints - New Routes

### New Endpoints Added:

1. **POST /api/agent/autonomous/reflect-relate**
   - Body: `{"target_entities": [...], "max_depth": 2, "top_n": 20}`
   - Returns: Report with potential_relations, investigation_tasks, statistics

2. **POST /api/agent/autonomous/investigate-crawl**
   - Body: `{"investigation_tasks": [...], "max_entities": 10, ...}`
   - Returns: Report with crawl_plans, crawl_results, statistics

3. **POST /api/agent/autonomous/combined**
   - Body: `{"target_entities": [...], "max_entities": 10, ...}`
   - Returns: Combined report with both phases

4. **POST /api/agent/autonomous/stop**
   - Body: `{"process_id": "reflect_relate_1_..."}`
   - Returns: `{"success": true, "status": "stopping"}`

5. **GET /api/agent/autonomous/processes**
   - Returns: `{"processes": [{"process_id": "...", "status": "running", ...}]}`

### Updated Endpoint:

6. **GET /api/agent/status**
   - Now includes new modes in the modes array:
     `["deep_rag", "reflect_relate", "investigate_crawl", "combined_autonomous", "autonomous_discover"]`

## Process Lifecycle

```
┌──────────────┐
│ User Action  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────┐
│ Create Process Entry     │
│ - Generate process_id    │
│ - Set status: "running"  │
│ - Record start time      │
└──────┬───────────────────┘
       │
       ▼
┌──────────────────────────┐
│ Execute Action           │
│ - Periodic stop checks   │
│ - Update progress        │
│ - Track current_task     │
└──────┬───────────────────┘
       │
       ▼
     ┌─┴─┐
     │ ? │ Stop requested?
     └─┬─┘
       │
   Yes │ No
       │
   ┌───▼───────────────┐  ┌────────────────────┐
   │ Set status:       │  │ Set status:        │
   │ "stopped"         │  │ "completed"        │
   │ Add timestamp     │  │ Add results        │
   └───────────────────┘  └────────────────────┘
```

## Color Themes

Each action has a distinct color theme for visual clarity:

- **Reflect & Relate**: Indigo (#6366F1)
- **Investigate Crawl**: Blue (#3B82F6)
- **Combined Mode**: Purple (#A855F7)
- **Classic Discovery**: Slate (#64748B)

These colors are used consistently across:
- Action selection cards
- Configuration labels
- Statistics panels
- Result sections

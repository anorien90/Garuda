# Multi-Step Task Validation & Persistent Memory

## Overview

This update finalizes the chat/agent system for multi-step task validation
using MCP-style tools. The dynamic task planner now supports:

- **Persistent short-term memory** stored in the selected database
- **Configurable online crawl toggle** (disable/enable per request)
- **`search_memory` MCP tool** for searching large working memory
- **Cancellation/interruption** via task queue integration (task_id wired through)
- **INSUFFICIENT_DATA escalation** triggering correct re-planning
- **Event-driven transparency** with SSE emissions per step
- **Token budget management** (~13000 token prompt window)
- **Full memory snapshot** returned in response for user transparency
- **Step-level progress reporting** via progress_callback for task queue integration
- **Aligned UI** across both popup and search-tab chat interfaces

## Architecture

### Multi-Step Processing Flow

```
User Question
    │
    ├─ 1. Create Plan (LLM generates tool steps)
    │     └─ Pattern reuse if similar past task found
    │
    ├─ 2. Execute Steps (iterative loop)
    │     ├─ search_local_data → RAG + SQL + Graph lookup
    │     ├─ crawl_external_data → Web search + crawl (if enabled)
    │     ├─ reflect_findings → LLM evaluates data sufficiency
    │     ├─ store_memory_data → Persist to DB + in-memory dict
    │     ├─ get_memory_data → Retrieve from working memory
    │     └─ search_memory → Keyword search across memory entries
    │
    ├─ 3. Evaluate Step (INSUFFICIENT_DATA → re-plan)
    │     └─ Stores insufficient marker in memory for transparency
    │
    ├─ 4. Evaluate Plan (LLM checks if answer is ready)
    │     └─ If done → return answer; else → next step or re-plan
    │
    ├─ 5. Cancellation Check (every step)
    │     └─ Cooperative cancellation via task_id in DB
    │
    └─ 6. Final Summary (if plan exhausted without answer)
```

### Persistent Memory (Database-backed)

Working memory is stored in `chat_memory_entries` table:

| Column      | Type    | Description                          |
|-------------|---------|--------------------------------------|
| plan_id     | UUID    | FK to chat_plans                     |
| key         | String  | Memory entry key                     |
| value_json  | JSON    | Memory entry value                   |
| step_index  | Integer | Step that wrote this entry           |
| tool_name   | String  | Tool that produced this entry        |

Memory is persisted after every step execution, so it survives:
- Process restarts
- Network interruptions
- Task cancellation and resumption

### Token Budget Management

The system uses a configurable token budget (default 13,000 tokens)
to prevent prompt overflow:

- **Plan creation prompts** are truncated to `max_prompt_tokens × 4` chars
- **Plan evaluation prompts** use half the budget for memory data
- **Final summary prompts** use half the budget for memory data
- Memory summaries in plan prompts are capped at 2,000 chars

## Configuration

### New Settings

| Setting                        | Env Variable                        | Default  | Description                         |
|-------------------------------|-------------------------------------|----------|-------------------------------------|
| `chat_crawl_enabled`          | `GARUDA_CHAT_CRAWL_ENABLED`        | `true`   | Global crawl toggle                 |
| `chat_max_prompt_tokens`      | `GARUDA_CHAT_MAX_PROMPT_TOKENS`    | `13000`  | Max token budget for prompts        |

### Per-Request Overrides

The `/api/chat` endpoint accepts `crawl_enabled` in the request body:

```json
{
  "question": "Find all GPUs from NVIDIA and AMD and compare flagships",
  "crawl_enabled": false,
  "use_planner": true
}
```

## MCP Tools

| Tool                 | Description                                           |
|---------------------|-------------------------------------------------------|
| `search_local_data` | RAG + SQL + Graph lookup                              |
| `crawl_external_data` | Web search + intelligent crawl (respects crawl gate) |
| `reflect_findings`  | LLM reflection on gathered data                       |
| `store_memory_data` | Store key/value to persistent working memory          |
| `get_memory_data`   | Retrieve data from working memory                     |
| `search_memory`     | Keyword search across memory (for large memory)       |
| `create_plan`       | Generate/regenerate a multi-step plan                 |
| `store_step_to_plan`| Append a step to the current plan                     |
| `eval_step_from_plan`| Evaluate a single step's outcome                     |
| `evaluate_plan`     | Evaluate the whole plan against the original request  |

## INSUFFICIENT_DATA Escalation

The system correctly triggers INSUFFICIENT_DATA in these scenarios:

1. **`search_local_data`** returns 0 hits → step fails → re-plan
2. **`crawl_external_data`** is disabled or errors → step fails → re-plan
3. **`reflect_findings`** returns `sufficient: false` → step fails → re-plan
4. **Any step fails** → error logged, remaining steps invalidated, re-plan

Each insufficient escalation stores a marker in memory:
```json
{"_insufficient_step_3": {"tool": "search_local_data", "reason": "INSUFFICIENT_DATA"}}
```

## UI Changes

### Aligned Chat Interfaces
Both chat forms (popup overlay and search-tab AI Chat mode) now have
identical capabilities and consistent styling:
- Larger text areas (4 rows) for complex multi-part questions
- Description banner explaining multi-step planning, memory, and cancellation
- Matching green "💬 Ask AI" submit buttons
- All toggles: 🧩 Planner, 🤖 Auto, 🌐 Online Crawl

### Step-by-Step Plan Visualization
The response UI now renders each plan step as a detailed card with:
- Status icon (✅ completed, ❌ failed, ⏭️ skipped, ⏳ pending)
- Tool name badge, step number, and description
- Colour-coded borders per status
- Summary line (e.g. "5 – 3 completed, 1 failed, 1 skipped")

### Enhanced Memory Display
The response now includes `memory_snapshot` (full key/value pairs)
instead of just `memory_keys`. The UI renders each memory entry
with a preview of its value (up to 300 chars) in a collapsible section.
Insufficient-data markers (`_insufficient_step_N`) are highlighted in red.

### Sources Referenced Section
All sources consulted during the plan are listed in a collapsible section
for full transparency of the research path.

### Progress During Execution
While the task is running (queued execution via task queue):
- Progress bar shows percentage (5 % → 90 % → 100 %)
- Step-level messages display tool badges (e.g. "Step 3: reflect findings")
- Cancel button allows the user to interrupt execution at any time

### Crawl Disabled Badge
When crawl is disabled, a "🚫 Crawl Disabled" badge is shown in the
response metadata.

### Event Transparency
Every step emits SSE events that appear in the event stream:
- `plan_created` - Plan initialized
- `plan_creating` - Plan revision started
- `step_executing` - Step started with tool name and description
- `step_completed` - Step finished with status
- `step_insufficient` - INSUFFICIENT_DATA triggered
- `plan_cancelled` - User cancelled the task
- `plan_summarizing` - Final summary being generated
- `plan_done` - Plan finished with final status

## Task Queue Integration

The task queue handler (`_handle_agent_chat`) now uses the TaskPlanner
directly instead of legacy `chat_async`. This means queued chat tasks:

1. Use the full multi-step planner with all MCP tools
2. Pass `task_id` for cooperative cancellation checks at every step
3. Pass `crawl_enabled` from the user's request
4. Report step-level progress via `progress_callback` → `tq.update_progress()`
5. Fall back to legacy `chat_async` only if the planner fails

The `/api/agent/chat` route also passes `crawl_enabled` to the planner
in both direct (non-queued) and queued execution paths.

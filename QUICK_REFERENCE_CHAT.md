# Chat UI Step Tracking - Quick Reference

## Response Fields (New)

### `current_step` (string)
Currently executing phase:
- `"phase1_initial_rag"` - Initial local search
- `"phase2_retry_paraphrasing"` - Retry with alternative queries
- `"phase3_web_crawling"` - Web search/crawl in progress
- `"phase4_final_local_lookup"` - Final local search after crawling

### `final_step` (string)  
Conclusive outcome state:

**Success (✅)**
- `"phase1_local_lookup"` - Immediate success
- `"phase2_local_lookup_after_retry"` - Success after retry
- `"phase4_local_lookup_after_cycle_N"` - Success after N cycles
- `"phase4_local_lookup_success"` - Success after max cycles

**Warning (⚡)**
- `"phase4_local_lookup_insufficient_after_all_cycles"` - Partial answer

**Error (⚠️)**
- `"error_no_urls_found_after_all_cycles"` - No URLs found
- `"error_fallback_answer_generated"` - Fallback used
- `"unknown_state"` - Unexpected state

---

## UI Badge Colors

```javascript
// Green - Success
if (finalStep.includes('success') || finalStep.includes('local_lookup')) {
  badge = 'green'  // ✅ Completed
}

// Amber - Warning
if (finalStep.includes('insufficient')) {
  badge = 'amber'  // ⚡ Final State
}

// Red - Error  
if (finalStep.startsWith('error')) {
  badge = 'red'    // ⚠️ Final State
}
```

---

## State Machine Flow

```
START
  ↓
Phase 1: Initial RAG
  ├─ Sufficient? → [END: phase1_local_lookup] ✅
  └─ Insufficient → Phase 2
              ↓
Phase 2: Retry with Paraphrasing
  ├─ Sufficient? → [END: phase2_local_lookup_after_retry] ✅
  └─ Insufficient → Phase 3
              ↓
Phase 3: Web Crawling (1 to N cycles)
  ├─ No URLs? → [END: error_no_urls_found_after_all_cycles] ⚠️
  └─ For each cycle:
      ├─ Sufficient? → [END: phase4_local_lookup_after_cycle_N] ✅
      └─ Continue to next cycle
              ↓
Phase 4: Final Local Lookup
  ├─ Sufficient? → [END: phase4_local_lookup_success] ✅
  └─ Insufficient → [END: phase4_local_lookup_insufficient_after_all_cycles] ⚡
              ↓
Fallback Check
  └─ No answer? → [END: error_fallback_answer_generated] ⚠️
```

---

## Testing Quick Reference

### Run All New Tests
```bash
pytest tests/test_chat_final_step_tracking.py -v
```

### Test Specific Scenario
```bash
pytest tests/test_chat_final_step_tracking.py::TestChatFinalStepTracking::test_phase1_local_lookup_success -v
```

### Test Classes
- `TestChatFinalStepTracking` - 8 tests for all final states
- `TestChatStepProgression` - 4 tests for phase progression
- `TestChatMultipleCyclesBehavior` - 4 tests for cycle behavior

---

## API Usage Examples

### Check if Success
```python
response = api_chat(question="...")
if response['final_step'].startswith('phase') and 'error' not in response['final_step']:
    print("Success!")
```

### Check How Many Cycles Used
```python
cycles = response['search_cycles_completed']
max_cycles = response['max_search_cycles']
if cycles > 0:
    print(f"Required web crawling: {cycles}/{max_cycles} cycles")
```

### Determine Result Quality
```python
if 'phase1' in response['final_step']:
    quality = "Excellent - immediate answer"
elif 'phase2' in response['final_step']:
    quality = "Good - answered after retry"
elif 'success' in response['final_step']:
    quality = "Good - answered after crawling"
elif 'insufficient' in response['final_step']:
    quality = "Partial - best effort answer"
else:
    quality = "Poor - fallback/error"
```

---

## Configuration

### Environment Variables
```bash
# Max search cycles (default: 3)
export GARUDA_CHAT_MAX_SEARCH_CYCLES=5

# RAG quality threshold (default: 0.7)
export GARUDA_CHAT_RAG_QUALITY_THRESHOLD=0.8

# Min high quality hits (default: 2)
export GARUDA_CHAT_MIN_HIGH_QUALITY_HITS=3

# Max pages per crawl (default: 5)
export GARUDA_CHAT_MAX_PAGES=10
```

### In Code
```python
from garuda_intel.config import Settings

settings = Settings()
settings.chat_max_search_cycles = 5
settings.chat_rag_quality_threshold = 0.8
settings.chat_min_high_quality_hits = 3
```

---

## Debugging

### Check Current Step
```javascript
console.log(`Current: ${response.current_step}`);
console.log(`Final: ${response.final_step}`);
```

### Trace Full Journey
```python
print(f"Retry attempted: {response['retry_attempted']}")
print(f"Online triggered: {response['online_search_triggered']}")
print(f"Cycles completed: {response['search_cycles_completed']}/{response['max_search_cycles']}")
print(f"Final step: {response['final_step']}")
```

### Event Log
Check Flask logs for detailed events:
```
[*] Phase 1: Initial RAG lookup
[*] RAG quality check: 0/5 high-quality hits
[*] Phase 2: Retry with paraphrasing and more hits
[*] Phase 3: Intelligent crawling triggered - Insufficient high-quality RAG results
[*] Search cycle 1/3 starting
[*] Cycle 1: Found 3 new URLs to crawl
...
```

---

## Common Patterns

### Early Success Pattern
```json
{
  "current_step": "phase1_initial_rag",
  "final_step": "phase1_local_lookup",
  "search_cycles_completed": 0,
  "online_search_triggered": false
}
```

### Full Cycle Pattern  
```json
{
  "current_step": "phase4_final_local_lookup",
  "final_step": "phase4_local_lookup_success",
  "search_cycles_completed": 3,
  "online_search_triggered": true,
  "retry_attempted": true
}
```

### Error Pattern
```json
{
  "current_step": "phase3_web_crawling",
  "final_step": "error_no_urls_found_after_all_cycles",
  "search_cycles_completed": 3,
  "live_urls": []
}
```

---

## Metrics to Track (Optional)

```python
# Distribution of final steps
final_step_counts = {
    'phase1': 0,  # Immediate success rate
    'phase2': 0,  # Retry success rate
    'phase4_after_cycle': 0,  # Crawl success rate
    'insufficient': 0,  # Partial answer rate
    'error': 0  # Error rate
}

# Average cycles needed
avg_cycles = total_cycles / total_requests

# Success rate by phase
phase1_success = phase1_count / total_requests
phase2_success = phase2_count / total_requests
phase4_success = phase4_count / total_requests
```

---

## Files Reference

**Modified:**
- `src/garuda_intel/webapp/routes/search.py` - Backend logic
- `src/garuda_intel/webapp/static/render-chat.js` - UI display
- `README.md` - User documentation

**Created:**
- `tests/test_chat_final_step_tracking.py` - Test suite
- `FINAL_SUMMARY.md` - Complete summary
- `IMPLEMENTATION_SUMMARY.md` - Technical details
- `CHAT_UI_VISUAL_EXAMPLES.md` - UI examples

---

## Support

For issues or questions:
1. Check `FINAL_SUMMARY.md` for overview
2. Check `IMPLEMENTATION_SUMMARY.md` for technical details
3. Check `CHAT_UI_VISUAL_EXAMPLES.md` for UI examples
4. Review test cases in `tests/test_chat_final_step_tracking.py`

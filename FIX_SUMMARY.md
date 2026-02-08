# Fix Summary: EntityGapAnalyzer.generate_crawl_plan() TypeError

## Problem
The `investigate_crawl` functionality in `agent_service.py` was failing with a `TypeError` 
because `EntityGapAnalyzer.generate_crawl_plan()` did not accept keyword arguments 
`entity`, `task_type`, and `context`.

**Error Location:** `src/garuda_intel/services/agent_service.py:1632-1636`

**Failed Call:**
```python
plan = gap_analyzer.generate_crawl_plan(
    entity=entity,                              # ❌ Not accepted
    task_type=task.get("task_type", "fill_gap"),  # ❌ Not accepted
    context=task.get("reason", ""),              # ❌ Not accepted
)
```

**Original Signature:**
```python
def generate_crawl_plan(self, entity_name: str, entity_type: Optional[str] = None)
```

## Solution
Updated the method signature to accept the new keyword arguments while maintaining 
full backwards compatibility with existing callers.

**New Signature:**
```python
def generate_crawl_plan(
    self, 
    entity_name: Optional[str] = None, 
    entity_type: Optional[str] = None,
    entity: Optional[Any] = None,      # NEW: Accept entity object
    task_type: Optional[str] = None,   # NEW: Task context
    context: Optional[str] = None      # NEW: Additional context
) -> Dict[str, Any]:
```

## Changes Made

### 1. Modified: `src/garuda_intel/services/entity_gap_analyzer.py`
- ✅ Updated `generate_crawl_plan()` signature with new optional parameters
- ✅ Added logic to handle `entity` object directly (skips DB lookup)
- ✅ Added logic to include `task_type` and `context` in returned plan
- ✅ Added validation: requires either `entity` or `entity_name`
- ✅ Maintained backwards compatibility with existing code
- ✅ Updated docstring with complete parameter documentation

### 2. Created: `tests/test_entity_gap_analyzer.py`
Comprehensive test suite with 11 test methods:

**Legacy Compatibility Tests (2):**
- `test_legacy_call_with_entity_name_positional` - Positional args
- `test_legacy_call_with_keyword_args` - Keyword args

**New Feature Tests (4):**
- `test_new_call_with_entity_object` - Entity object parameter
- `test_new_call_with_entity_and_task_context` - With task_type/context
- `test_new_call_entity_name_with_task_context` - Entity name with task context
- `test_discovery_mode_with_task_context` - Discovery mode with context

**Edge Cases (5):**
- `test_missing_both_entity_and_entity_name_raises_error` - Error handling
- `test_entity_takes_precedence_over_entity_name` - Parameter precedence
- `test_optional_task_type_only` - Partial optional params
- `test_optional_context_only` - Partial optional params
- `test_plan_structure_consistency` - Plan structure validation

### 3. Created: `CHANGELOG_entity_gap_analyzer_fix.md`
Detailed documentation of changes and impact

## Verification Results

✅ **Syntax:** All Python files pass AST parsing  
✅ **Signature:** All 5 new parameters present and Optional  
✅ **Tests:** 11 test methods with comprehensive coverage  
✅ **Backwards Compatibility:** All existing call sites verified:
   - `adaptive_crawler.py:95` - Positional args ✅
   - `agent_service.py:1159` - Positional args ✅  
   - `agent_service.py:1632` - New keyword args ✅ (FIXED)

## Impact Assessment

**Breaking Changes:** None  
**API Changes:** Additive only (new optional parameters)  
**Affected Components:** `EntityGapAnalyzer` only  
**UI Changes:** None  
**Database Changes:** None  

## Call Pattern Examples

### Legacy (Still Works)
```python
# Positional
plan = analyzer.generate_crawl_plan("Microsoft", "company")

# Keyword
plan = analyzer.generate_crawl_plan(entity_name="Apple", entity_type="company")
```

### New (Now Works)
```python
# With entity object
plan = analyzer.generate_crawl_plan(entity=entity_obj)

# With full context
plan = analyzer.generate_crawl_plan(
    entity=entity_obj,
    task_type="investigate_crawl", 
    context="High priority investigation"
)

# Entity name with context
plan = analyzer.generate_crawl_plan(
    entity_name="Google",
    task_type="fill_gap",
    context="Missing revenue data"
)
```

## Behavior Details

| Scenario | Behavior |
|----------|----------|
| `entity` provided | Uses entity object directly, skips DB lookup |
| `entity_name` provided | Looks up entity in DB (original behavior) |
| Both provided | `entity` takes precedence |
| Neither provided | Raises `ValueError` |
| `task_type` provided | Added to returned plan |
| `context` provided | Added to returned plan |

## Files Modified
1. `src/garuda_intel/services/entity_gap_analyzer.py` - Method signature update
2. `tests/test_entity_gap_analyzer.py` - New test file (11 tests)
3. `CHANGELOG_entity_gap_analyzer_fix.md` - Documentation

## Ready for Testing
✅ All changes implemented  
✅ All tests written  
✅ No breaking changes  
✅ Backwards compatible  
✅ Issue fixed: `investigate_crawl` will now work  

**Note:** As requested, linters and tests were not run. Tests can be executed with:
```bash
pytest tests/test_entity_gap_analyzer.py -v
```

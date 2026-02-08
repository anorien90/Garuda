# Entity Gap Analyzer Fix - Signature Update

## Issue
`investigate_crawl` was failing with `TypeError` because `EntityGapAnalyzer.generate_crawl_plan()` 
did not accept the `entity` keyword argument.

**Error location:** `garuda_intel/services/agent_service.py` line ~1632

**Stack trace:** Called `gap_analyzer.generate_crawl_plan(entity=entity, task_type=..., context=...)`
but the method only accepted `entity_name` and `entity_type` parameters.

## Solution
Updated `EntityGapAnalyzer.generate_crawl_plan()` method signature to support both:

1. **Legacy mode** (backwards compatible):
   - `generate_crawl_plan(entity_name, entity_type)` - lookup entity by name
   
2. **New mode** (for investigate_crawl):
   - `generate_crawl_plan(entity=entity_obj, task_type="...", context="...")` - use provided entity

### New Signature
```python
def generate_crawl_plan(
    self, 
    entity_name: Optional[str] = None, 
    entity_type: Optional[str] = None,
    entity: Optional[Any] = None,
    task_type: Optional[str] = None,
    context: Optional[str] = None
) -> Dict[str, Any]:
```

### Behavior
- **When `entity` is provided**: Uses the entity object directly, skips DB lookup
- **When `entity_name` is provided**: Lookups entity in DB by name (legacy behavior)
- **When both provided**: `entity` takes precedence over `entity_name`
- **When neither provided**: Raises `ValueError`
- **Optional `task_type` and `context`**: Added to plan if provided

## Changes Made

### Modified Files
1. **src/garuda_intel/services/entity_gap_analyzer.py**
   - Updated `generate_crawl_plan()` method signature
   - Added validation to ensure either `entity` or `entity_name` is provided
   - Added logic to handle `entity` object directly
   - Added `task_type` and `context` to returned plan when provided
   - Maintained backwards compatibility with existing callers

### New Files
2. **tests/test_entity_gap_analyzer.py**
   - Comprehensive test suite with 11 test cases
   - Tests legacy compatibility (positional and keyword args)
   - Tests new entity object parameter
   - Tests task_type and context parameters
   - Tests edge cases (missing params, precedence, optional params)
   - Tests plan structure consistency

## Backwards Compatibility
✅ All existing call sites continue to work:
- `adaptive_crawler.py:95` - Uses `(entity_name, entity_type)` positional
- `agent_service.py:1159` - Uses `(entity_name, entity_kind)` positional
- `agent_service.py:1632` - NEW: Uses `entity=entity, task_type=..., context=...` keywords

## Test Coverage
- 11 test methods covering:
  - Legacy positional arguments
  - Legacy keyword arguments
  - New entity object parameter
  - Task type and context parameters
  - Discovery mode with task context
  - Error handling for missing parameters
  - Parameter precedence rules
  - Optional parameters
  - Plan structure consistency

## Verification
✅ Python syntax validated
✅ Signature includes all required parameters
✅ All call sites analyzed and confirmed compatible
✅ Test file structure verified
✅ No breaking changes to existing functionality

## Impact
- **Minimal**: Only affects the method signature
- **No UI changes**: Backend-only modification
- **Zero breaking changes**: Existing code continues to work
- **Enables investigate_crawl**: Fixes the TypeError in agent_service.py

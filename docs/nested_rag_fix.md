# Nested RAG Retrieval Fix

## Overview

This document describes the fixes applied to ensure the chat endpoint works correctly with nested RAG retrieval results from the multidimensional search (combining embedding-based and graph-based search).

## Problem

The chat system's `gather_hits` function uses `agent_service.multidimensional_search()` to retrieve results from graph traversal. These results could contain:

1. **Nested data structures** in intelligence data fields (nested dicts/lists)
2. **Missing or malformed fields** (e.g., missing `combined_score`, `url`, `text`)
3. **Inconsistent data types** (e.g., score fields that aren't numbers)
4. **Nested lists** in metadata fields (e.g., `sources: ["embedding", "graph"]`)

Without proper handling, these nested structures could cause:
- Type errors when processing results
- Poor quality text snippets (Python repr instead of readable JSON)
- Inconsistent scoring when fields are missing
- Potential failures in downstream processing

## Solution

### 1. Improved Graph Result Processing in `search.py`

**File**: `src/garuda_intel/webapp/routes/search.py`

**Changes** (lines 317-355):
- Added explicit field extraction with null coalescing (`or ""`)
- Added type checking for score fields with proper fallback chain
- Added flattening of nested text structures to JSON format
- Added per-result error handling with try/except to continue processing even if individual results are malformed
- Increased text limit to 1000 chars for better context

**Benefits**:
- Robust handling of missing fields
- Proper conversion of nested structures to strings
- Graceful degradation when individual results are malformed
- Better context for LLM synthesis

### 2. Better Intelligence Data Conversion in `agent_service.py`

**File**: `src/garuda_intel/services/agent_service.py`

**Changes** (lines 786-810):
- Convert nested intelligence data (dicts/lists) to JSON format instead of Python repr
- Add fallback to string conversion if JSON serialization fails
- Ensure all required fields have defaults (empty strings for missing fields)
- Explicitly initialize `url` field

**Benefits**:
- Readable JSON format instead of `{'key': 'value'}` Python syntax
- More compact representation (separators without spaces)
- Proper handling of complex nested structures
- Better context quality for RAG

### 3. Cleaner Result Combination Logic

**File**: `src/garuda_intel/services/agent_service.py`

**Changes** (lines 845-901):
- Create clean copies of results instead of modifying originals
- Replace nested `sources` list with simple `source_types` string
- Ensure consistent field structure across all results
- Explicit field extraction for all expected fields

**Benefits**:
- No nested list structures in final results
- Consistent field structure
- Easier to debug and maintain
- String concatenation (`"embedding+graph"`) instead of list

## Testing

### New Tests: `tests/test_nested_rag_fix.py`

Added comprehensive test coverage for:

1. **Graph result flattening** - Validates proper extraction from multidimensional_search results
2. **Nested intelligence data handling** - Tests JSON conversion of nested dicts/lists
3. **Nested text field flattening** - Ensures text fields that are dicts/lists get converted to JSON
4. **Malformed score handling** - Tests handling of invalid score types and missing scores
5. **Missing combined_score handling** - Tests fallback to regular score field
6. **Empty graph results** - Tests handling of empty or missing results
7. **Deduplication with graph hits** - Tests merging of RAG, graph, and SQL results
8. **Graph hits without URLs** - Tests preservation of results without URL fields

All tests pass successfully, validating the fix works as intended.

### Existing Tests: `tests/test_rag_chat.py`

All existing RAG chat logic tests continue to pass, confirming:
- No regression in existing functionality
- Backward compatibility maintained
- Core RAG prioritization logic intact

## Code Changes Summary

### Files Modified

1. `src/garuda_intel/services/agent_service.py`
   - Updated `_graph_based_search()` to better handle nested intelligence data
   - Updated `_combine_search_results()` to avoid nested structures

2. `src/garuda_intel/webapp/routes/search.py`
   - Enhanced graph result processing in `gather_hits()` with robust field extraction
   - Added type checking and nested structure flattening

### Files Added

1. `tests/test_nested_rag_fix.py` - Comprehensive test suite for the fixes

## Impact

### Positive Changes

- ✅ More robust handling of complex nested data structures
- ✅ Better JSON formatting for LLM context (compact, readable)
- ✅ Graceful handling of malformed or incomplete results
- ✅ No breaking changes to existing functionality
- ✅ Better error messages and logging

### Performance

- Minimal performance impact (JSON serialization is fast for small objects)
- Reduced potential for errors/exceptions during result processing
- More reliable RAG retrieval overall

## Future Improvements

Potential enhancements for future iterations:

1. **Schema validation** - Add Pydantic models for result validation
2. **Configurable text limits** - Make the 500/1000 char limits configurable
3. **Rich text extraction** - Better handling of HTML/Markdown in nested data
4. **Semantic deduplication** - Use embeddings to detect semantic duplicates beyond URL matching
5. **Result quality scoring** - Add quality metrics for graph vs embedding results

## Conclusion

The nested RAG fix ensures the chat system reliably handles complex graph traversal results from multidimensional search. The changes are minimal, focused, and maintain backward compatibility while significantly improving robustness.

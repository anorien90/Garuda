# Exoscale Authentication Error Handling Fix - Summary

## Problem Statement

The Exoscale adapter's `_api_request()` method was returning `None` for ALL API errors, including HTTP 401/403 authentication/authorization failures. This caused the calling methods (`_find_existing_instance()`, `_ensure_security_group()`, `ensure_instance()`) to interpret authentication failures as "resource not found" and attempt to create resources, leading to a cascade of 403 errors.

### Symptom
```
[ERROR] Exoscale API request failed: 403 Client Error: Forbidden for url: .../v2/instance
[INFO] No existing instance found, creating new one
[ERROR] Exoscale API request failed: 403 Client Error: Forbidden for url: .../v2/security-group
[INFO] Creating security group 'garuda-ollama-sg'
[ERROR] Exoscale API request failed: 403 Client Error: Forbidden for url: .../v2/security-group
[ERROR] Failed to create security group
[ERROR] Failed to create/find security group
```

## Solution

Added proper authentication error detection and exception handling:

### 1. New Exception Class (`src/garuda_intel/exoscale/adapter.py`)
Added `ExoscaleAuthError` exception class after imports:
```python
class ExoscaleAuthError(Exception):
    """Raised when Exoscale API returns authentication/authorization errors (401/403)."""
    pass
```

### 2. Enhanced Error Handling in `_api_request()` Method
Modified the exception handling to:
- **Catch `HTTPError` BEFORE generic `RequestException`** (since HTTPError is a subclass)
- **Raise `ExoscaleAuthError` for HTTP 401/403** with a helpful error message
- **Return `None` for other HTTP errors** (404, 500, etc.) - preserving existing behavior
- **Return `None` for non-HTTP errors** (connection errors, timeouts) - preserving existing behavior

```python
except requests.exceptions.HTTPError as e:
    if e.response is not None and e.response.status_code in (401, 403):
        self.logger.error(f"Exoscale API authentication failed: {e}")
        raise ExoscaleAuthError(
            f"Exoscale API authentication/authorization failed (HTTP {e.response.status_code}). "
            "Check your EXOSCALE_API_KEY and EXOSCALE_API_SECRET."
        ) from e
    self.logger.error(f"Exoscale API request failed: {e}")
    return None
except requests.exceptions.RequestException as e:
    self.logger.error(f"Exoscale API request failed: {e}")
    return None
```

### 3. Comprehensive Test Coverage (`tests/test_exoscale_adapter.py`)
Added 4 new test methods to ensure correct behavior:

#### In `TestAPIRequest` class:
1. `test_api_request_403_raises_auth_error` - Verifies 403 Forbidden raises ExoscaleAuthError
2. `test_api_request_401_raises_auth_error` - Verifies 401 Unauthorized raises ExoscaleAuthError
3. `test_api_request_500_returns_none` - Verifies 500 Server Error returns None (not exception)

#### In `TestEnsureInstance` class:
4. `test_ensure_instance_auth_error_propagates` - Verifies ExoscaleAuthError propagates up the call chain

## Files Modified

### `/home/runner/work/Garuda/Garuda/src/garuda_intel/exoscale/adapter.py`
- Added `ExoscaleAuthError` exception class (lines 23-25)
- Modified `_api_request()` method error handling (lines 164-170)

### `/home/runner/work/Garuda/Garuda/tests/test_exoscale_adapter.py`
- Updated import to include `ExoscaleAuthError` (line 97)
- Added 3 new test methods in `TestAPIRequest` class (lines 361-400)
- Added 1 new test method in `TestEnsureInstance` class (lines 641-647)

## Behavior Changes

### Before
- **401/403 errors**: Returned `None` → Caller tried to create resources → Cascade of 403 errors
- **404/500 errors**: Returned `None` → Caller handled appropriately
- **Connection errors**: Returned `None` → Caller handled appropriately

### After
- **401/403 errors**: Raises `ExoscaleAuthError` → Propagates to webapp → User sees clear auth error
- **404/500 errors**: Returns `None` → Caller handles appropriately (unchanged)
- **Connection errors**: Returns `None` → Caller handles appropriately (unchanged)

## Integration with Webapp

The webapp (`src/garuda_intel/webapp/app.py`) already has proper exception handling around adapter initialization (lines 57-77):

```python
try:
    exoscale_adapter = ExoscaleOllamaAdapter(...)
except Exception as e:
    logger.error(f"Failed to initialize Exoscale adapter: {e}")
    exoscale_adapter = None
```

Now when credentials are invalid:
1. `ExoscaleAuthError` is raised during adapter initialization
2. Exception is caught by webapp's try/except block
3. `exoscale_adapter` is set to `None`
4. User sees a single clear error message instead of a cascade of 403 errors

## Test Results

All 61 tests in `test_exoscale_adapter.py` pass successfully:
```
================================================= test session starts ==================================================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/runner/work/Garuda/Garuda
configfile: pyproject.toml
plugins: mock-3.15.1
collecting ... collected 61 items                                                                                                     

tests/test_exoscale_adapter.py .............................................................                     [100%]

================================================= 61 passed in 17.18s ==================================================
```

## Key Design Decisions

1. **Only 401 and 403 raise exceptions** - These are the only auth-related errors. Other HTTP errors (404, 500, etc.) continue to return `None` as callers expect this for "resource not found" scenarios.

2. **HTTPError caught before RequestException** - Since `HTTPError` is a subclass of `RequestException`, it must be caught first to check the status code.

3. **Helpful error message** - The exception message guides users to check their credentials.

4. **Preserved existing behavior** - Non-auth errors still return `None`, ensuring backward compatibility.

5. **No changes to webapp** - The webapp already has proper exception handling, so no changes were needed there.

## Verification

The fix successfully prevents the cascade of 403 errors and provides clear feedback when authentication fails, while preserving the existing behavior for all other error types.

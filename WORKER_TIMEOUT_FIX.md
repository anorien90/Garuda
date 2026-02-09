# Worker Timeout Fix for Ollama Exoscale Proxy

## Problem
During POST /api/generate requests, gunicorn workers were timing out because `ensure_instance()` in `app/exoscale_adapter.py` was blocking while waiting for instance creation. The `create_instance()` method could take up to 6 minutes (300s INSTANCE_STARTUP_TIMEOUT + 60s CLOUD_INIT_WAIT_TIME), causing worker timeouts.

## Solution
Implemented asynchronous instance provisioning to avoid blocking the HTTP request/worker:

### Changes to `exoscale_adapter.py`:

1. **Added provisioning state tracking**:
   - New instance variables: `provisioning_lock`, `provisioning_thread`, `provisioning_status`, `provisioning_error`
   - Status values: `idle`, `provisioning`, `ready`, `error`

2. **Refactored `create_instance()` method**:
   - **Before**: Blocking method that waited for instance to be fully provisioned
   - **After**: Non-blocking method that starts background thread and returns immediately
   - Returns `bool` indicating if provisioning started (vs returning URL)

3. **Added `_create_instance_blocking()` method**:
   - Internal method that does the actual blocking work
   - Runs in background thread
   - Updates `provisioning_status` as it progresses

4. **Updated `ensure_instance()` method**:
   - Returns URL if instance is ready
   - Returns `None` if provisioning is in progress
   - Checks provisioning status and doesn't start duplicate provisioning

5. **Added `get_provisioning_status()` method**:
   - Returns current status: `status`, `error` (if any), `remote_url` (if ready)

### Changes to `app.py`:

1. **Added `get_provisioning_status()` helper function**:
   - Wrapper around adapter's `get_provisioning_status()`

2. **Updated `proxy_request()` function**:
   - Now handles `None` return from `ensure_remote_instance()`
   - Returns HTTP 503 with `"provisioning": true` flag when instance is being provisioned
   - Returns HTTP 503 with error details if provisioning failed
   - Provides clear error messages to guide client retry behavior

3. **Updated `/status` endpoint**:
   - Now includes `provisioning_status` field
   - Shows `error` field if provisioning failed

### Changes to `README.md`:

1. **Updated "How It Works" section**:
   - Documents asynchronous provisioning behavior
   - Explains that first request returns 503 during provisioning
   - Clarifies that clients should retry with backoff

2. **Updated status endpoint documentation**:
   - Added `provisioning_status` field and possible values
   - Added example showing error state

3. **Updated troubleshooting section**:
   - Documents new async behavior
   - Explains how clients should handle 503 responses
   - Provides guidance on monitoring with `/status` endpoint

### Changes to `tests/test_ollama_exoscale.py`:

1. **Added new test `test_proxy_request_provisioning()`**:
   - Tests behavior when instance is being provisioned
   - Verifies 503 response with `provisioning: true` flag

2. **Updated `test_proxy_request_no_instance()`**:
   - Now mocks `get_provisioning_status()` as well

3. **Added `test_async_create_instance()`**:
   - Tests that `create_instance()` returns immediately
   - Verifies background thread is started
   - Checks provisioning status transitions

4. **Added `test_ensure_instance_with_running()`**:
   - Tests fast path when instance is already running
   - Verifies immediate URL return

## Behavior Changes

### Before:
```
Client -> POST /api/generate
  -> ensure_instance() [BLOCKS 6+ minutes]
  -> create_instance() [BLOCKS]
  -> Worker timeout after ~30s
  -> Request fails
```

### After:
```
Client -> POST /api/generate
  -> ensure_instance() returns None
  -> Returns 503 with {"provisioning": true}
  [Background thread provisions instance]
  
Client retries after 30s
  -> ensure_instance() returns None (still provisioning)
  -> Returns 503 with {"provisioning": true}
  
Client retries again
  -> ensure_instance() returns URL (ready!)
  -> Request proxied successfully
```

## Testing

All 28 tests pass:
```bash
$ python -m pytest tests/test_ollama_exoscale.py -v
======================== 28 passed in 5.43s =========================
```

Key test scenarios:
- Async instance creation doesn't block
- Provisioning status tracking works correctly
- Proxy returns 503 during provisioning with retry guidance
- Running instances return URL immediately
- Error states are properly handled

## Backwards Compatibility

The changes maintain backwards compatibility:
- Existing behavior for running instances unchanged (immediate URL return)
- Existing behavior for stopped instances unchanged (starts and waits ~30-60s)
- Only new instance creation is asynchronous
- API response format extended (added `provisioning` flag to errors)

## Production Deployment

No configuration changes needed:
- Same environment variables
- Same Docker setup
- Gunicorn timeout can remain at default (30s)
- Clients should implement retry logic with exponential backoff

Recommended client behavior:
```python
import time
import requests

max_retries = 20
retry_delay = 30  # seconds

for i in range(max_retries):
    response = requests.post(url, json=data)
    
    if response.status_code == 503:
        error_data = response.json()
        if error_data.get("provisioning"):
            print(f"Instance provisioning, retry {i+1}/{max_retries}...")
            time.sleep(retry_delay)
            continue
    
    # Handle success or other errors
    break
```

## Summary

The fix successfully prevents worker timeouts by making instance provisioning asynchronous. Requests now return immediately with a 503 status and provisioning flag, allowing clients to retry until the instance is ready. The solution is minimal, maintains backwards compatibility, and follows the repository's coding standards.

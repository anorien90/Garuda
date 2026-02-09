# Exoscale GPU Instance Type Lookup Fix

## Problem

The Exoscale cloud adapter was failing to launch GPU instances because the code attempted to match instance types against a non-existent `name` field. The Exoscale API `list-instance-types` endpoint returns objects with separate `family` and `size` fields instead:

```json
{
  "id": "some-uuid",
  "family": "gpua5000",
  "size": "small",
  "cpus": 4,
  "gpus": 1,
  "memory": 32768,
  "zones": ["at-vie-2"],
  "authorized": true
}
```

The old code was doing:
```python
if itype.get("name") == self.instance_type:  # "name" field doesn't exist!
    return itype.get("id")
```

## Solution

### 1. Fixed Instance Type Lookup

**Both adapters now:**
- Parse the `instance_type` config value (e.g., `gpua5000.small`) into `family` and `size` components
- Match against the API's `family` and `size` fields separately
- Verify zone availability (`zone_name in itype.get("zones", [])`)
- Include fallback logic: if exact family match fails, try adding "gpu" prefix (e.g., `a5000` → `gpua5000`)
- Log available GPU instance types on failure for debugging

**Implementation:**
```python
def _find_instance_type_id(self) -> Optional[str]:
    """Find the instance type ID by family and size."""
    # Parse family.size format
    parts = self.instance_type.split(".", 1)
    if len(parts) != 2:
        self.logger.error(f"Invalid instance type format '{self.instance_type}', expected 'family.size'")
        return None
    
    target_family, target_size = parts
    
    # Try exact match first
    for itype in instance_types:
        if (itype.get("family") == target_family 
                and itype.get("size") == target_size
                and self.zone_name in itype.get("zones", [])):
            return itype.get("id")
    
    # Fallback: try with "gpu" prefix
    if not target_family.startswith("gpu"):
        gpu_family = f"gpu{target_family}"
        for itype in instance_types:
            if (itype.get("family") == gpu_family 
                    and itype.get("size") == target_size
                    and self.zone_name in itype.get("zones", [])):
                return itype.get("id")
    
    # Log available GPU types for debugging
    # ...
```

### 2. Added GPU-Aware Cloud-Init

**New helper method:**
```python
def _is_gpu_instance(self) -> bool:
    """Check if the configured instance type is a GPU instance."""
    family = self.instance_type.split(".", 1)[0] if "." in self.instance_type else self.instance_type
    return family.startswith("gpu")
```

**For GPU instances, cloud-init now:**
- Installs NVIDIA driver 570 and container toolkit before Docker
- Runs Ollama container with `--gpus all` flag

**For non-GPU instances:**
- Standard Docker installation only
- Runs Ollama container without GPU flags

**Example cloud-init diff:**
```bash
# GPU instances include:
apt-get install -y nvidia-driver-570 nvidia-container-toolkit
docker run -d --gpus all --name ollama -p 0.0.0.0:11434:11434 ollama/ollama:latest

# Non-GPU instances:
docker run -d --name ollama -p 0.0.0.0:11434:11434 ollama/ollama:latest
```

### 3. Updated Ubuntu Template

Changed default OS template from **Ubuntu 22.04 LTS** to **Ubuntu 24.04 LTS** across all configuration files:
- `ollama-exoscale/Dockerfile`
- `docker-compose.yml`
- `src/garuda_intel/config.py`
- `src/garuda_intel/exoscale/adapter.py`

## Files Modified

1. **ollama-exoscale/exoscale_adapter.py** - Python Exoscale SDK adapter
   - Fixed `_find_instance_type_id()` method (lines 160-217)
   - Added `_is_gpu_instance()` helper (lines 155-158)
   - Updated `_generate_cloud_init()` for GPU support (lines 281-350)

2. **src/garuda_intel/exoscale/adapter.py** - REST API adapter
   - Fixed `_find_instance_type()` method (lines 199-255)
   - Added `_is_gpu_instance()` helper (lines 194-197)
   - Updated `_generate_cloud_init()` for GPU support (lines 299-395)

3. **ollama-exoscale/Dockerfile** - Updated template env var (line 16)
4. **docker-compose.yml** - Updated template env var (line 68)
5. **src/garuda_intel/config.py** - Updated template defaults (lines 106, 182)

## Testing

✅ **Manual Testing Performed:**
- GPU instance detection correctly identifies `gpua5000.small` as GPU instance
- Non-GPU instances (e.g., `standard.medium`) correctly detected as non-GPU
- Instance type parsing works for `family.size` format
- Cloud-init scripts generated correctly for both GPU and non-GPU instances:
  - GPU: Contains NVIDIA drivers + `--gpus all`
  - Non-GPU: Does not contain GPU-related components
- Both adapters import successfully without errors
- Config imports successfully with updated Ubuntu 24.04 template

✅ **Security Check:**
- CodeQL analysis: 0 alerts found

## Usage

**For GPU instances (A5000, A6000, etc.):**
```bash
# Environment variable
export EXOSCALE_INSTANCE_TYPE="gpua5000.small"

# Or in docker-compose.yml
EXOSCALE_INSTANCE_TYPE=gpua5000.small

# Supported formats:
# - gpua5000.small (exact match)
# - a5000.small (auto-resolves to gpua5000.small)
```

**For CPU instances:**
```bash
export EXOSCALE_INSTANCE_TYPE="standard.medium"
```

## Backwards Compatibility

✅ The changes are backwards compatible:
- Existing CPU instance type configurations continue to work
- The "gpu" prefix fallback ensures `a5000.small` resolves to `gpua5000.small`
- Template update to Ubuntu 24.04 is safe (22.04 is older, less secure)

## Related Documentation

See also:
- `EXOSCALE_QUICKSTART.md` - Quick start guide for Exoscale deployment
- Exoscale API documentation: https://openapi-v2.exoscale.com/

## Commit

```
commit 4d8cacf
Author: GitHub Copilot <copilot@github.com>
Date:   [timestamp]

    Fix GPU instance type lookup on Exoscale and add GPU support
    
    - Fix instance type matching to use family+size fields instead of non-existent 'name' field
    - Parse instance_type config (e.g., 'gpua5000.small') into family and size components
    - Match against Exoscale API's family and size fields separately
    - Add fallback to try 'gpu' prefix (e.g., 'a5000' -> 'gpua5000')
    - Check zone availability during instance type lookup
    - Log available GPU instance types on lookup failure for debugging
    
    - Add GPU detection helper method _is_gpu_instance()
    - For GPU instances, install NVIDIA driver 570 and container toolkit in cloud-init
    - For GPU instances, run Ollama container with --gpus all flag
    - For non-GPU instances, use standard docker run without GPU flags
    
    - Update Ubuntu template from 22.04 to 24.04 LTS across all configs
```

## Security Summary

No security vulnerabilities were introduced by these changes. The modifications are limited to:
- Fixing API field matching (from non-existent `name` to correct `family`/`size` fields)
- Adding GPU driver installation for GPU instances
- Updating Ubuntu version to a newer LTS release
- Adding defensive logging for debugging

All changes were validated with CodeQL security scanning - 0 alerts found.

# Design: Automatic Orphan Service Removal in update.cs

## Overview

Enhance `scripts/update.cs` to automatically detect and remove services that are no longer in the configuration but still have running containers or exist in the `services/` directory.

## Problem

When a service is removed from `stack.local.json` (or `stack.json`), the `update.cs` script does not stop or remove its containers. Users must manually run `docker compose down` before deleting the service directory.

## Solution

### Behavior

- Auto-remove orphaned services with a notice printed to console
- Run cleanup **before** updating active services
- Use `docker compose down -v` (safe because persistent data uses bind mounts to `${DATA_PATH}`, not Docker volumes)

### Detection Logic

Scan `services/` for all directories matching the `NN-name` pattern and compare against configured services:

```
For each directory in services/ matching NN-name pattern:
  If directory NOT in configured services list:
    If docker-compose.yml exists:
      Print "Removing orphaned service: {name}..."
      Run: docker compose down -v
      Print "✓ Removed {name}"
    Else:
      Print "⚠ Disabled service directory: {name} (no compose file)"
```

### Updated Flow

```
1. Git pull
2. Load config
3. Ensure networks exist
4. Remove orphaned services  ← NEW
5. Update configured services (existing logic)
```

## Files to Modify

| File | Change |
|------|--------|
| `scripts/update.cs` | Add orphan detection and removal logic before service updates |
| `README.md` | Add warning about not renaming the stack after services are started |

## README Warning

Add to the Configuration section:

> **Warning:** Do not rename `project_name` in `stack.json` after services have been started. The project name is used as a prefix for Docker containers and networks (e.g., `stack-n8n-1`). Changing it will:
> - Leave old containers running under the old name
> - Create duplicate containers under the new name
> - Cause `update.cs` orphan detection to miss the old containers
>
> If you must rename, first stop all services with `./scripts/stop.cs`, then rename.

## Data Safety

This approach is safe because:
- Persistent data is stored via bind mounts to `${DATA_PATH}/servicename`
- Docker volumes only contain ephemeral data
- `docker compose down -v` removes Docker volumes but does not touch bind mounts

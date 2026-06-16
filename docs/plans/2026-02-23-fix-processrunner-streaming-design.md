# Fix ProcessRunner Deadlock + Stream Output + Timeout

**Date:** 2026-02-23
**Status:** Approved

## Problem

The `ProcessRunner` class has a deadlock bug: it reads stdout synchronously to completion before reading stderr. If a child process (e.g. `docker compose up -d`) writes enough to stderr to fill the OS pipe buffer (~64KB), both processes deadlock permanently. Docker Compose writes pull progress and status messages to stderr, making this a frequent occurrence during `start.cs` and `update.cs`.

Additionally, scripts provide no progress visibility — users see "Starting service..." and then nothing until the command completes (or hangs).

## Solution

### 1. Fix deadlock in ProcessRunner.Run and RunInDir

Read stdout and stderr concurrently using background tasks:

```csharp
var outputTask = Task.Run(() => process.StandardOutput.ReadToEnd());
var errorTask = Task.Run(() => process.StandardError.ReadToEnd());
process.WaitForExit();
var output = outputTask.Result;
var error = errorTask.Result;
```

This prevents the pipe buffer deadlock while preserving the existing API.

### 2. Add RunStreaming method

New method that prints output in real-time:

```csharp
public static CommandResult RunStreaming(
    string command, string args, string workingDir,
    Dictionary<string, string>? envVars = null,
    int timeoutSeconds = 300)
```

- Uses `OutputDataReceived` / `ErrorDataReceived` event handlers to print lines as they arrive
- Streams both stdout and stderr to console with `  ` indent
- Still captures output in `CommandResult` for success/failure checking
- Kills the process and returns failure if `timeoutSeconds` exceeded

### 3. Update start.cs and update.cs

Switch `docker compose up -d`, `docker compose pull`, and `docker compose build` calls from `RunInDir` to `RunStreaming`.

Other scripts (stop.cs, status.cs) stay on `RunInDir` — the deadlock fix applies to them too, but they don't need streaming.

## Files Changed

- `scripts/lib/ProcessRunner.cs` — fix deadlock + add `RunStreaming`
- `scripts/start.cs` — use `RunStreaming`
- `scripts/update.cs` — use `RunStreaming`

## Example Output

Before:
```
▶ Starting 20-ragflow...
[hangs silently]
```

After:
```
▶ Starting 20-ragflow...
  Container stack-ragflow-1  Creating
  Container stack-ragflow-1  Created
  Container stack-ragflow-1  Starting
  Container stack-ragflow-1  Started
✓ 20-ragflow
```

Timeout:
```
▶ Starting 20-ragflow...
  Container stack-ragflow-1  Creating
  ✗ 20-ragflow - timed out after 300s
```

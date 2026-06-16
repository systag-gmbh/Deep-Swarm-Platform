# Fix ProcessRunner Deadlock + Streaming Output — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the deadlock in ProcessRunner that causes scripts to hang, add real-time streaming output for docker commands, and add timeout protection.

**Architecture:** Fix the root cause (synchronous stdout/stderr reads) in the shared `ProcessRunner` class, add a new `RunStreaming` method for long-running docker commands, then update the two affected scripts (`start.cs`, `update.cs`) to use it.

**Tech Stack:** .NET 10 file-based scripts, C# top-level statements, `System.Diagnostics.Process`

---

### Task 1: Fix deadlock in ProcessRunner.Run

**Files:**
- Modify: `scripts/lib/ProcessRunner.cs:21-38` (the `Run` method)

**Context:** The current code reads stdout to completion, then stderr. If a child process fills the stderr pipe buffer (~64KB) while we block on stdout, both processes deadlock. Fix by reading both streams concurrently.

**Step 1: Fix the concurrent read in `Run`**

Replace lines 32-35 in `scripts/lib/ProcessRunner.cs`:

```csharp
        // OLD (deadlock-prone):
        // var output = process!.StandardOutput.ReadToEnd();
        // var error = process.StandardError.ReadToEnd();
        // process.WaitForExit();

        // NEW (concurrent reads prevent pipe buffer deadlock):
        using var process = Process.Start(psi);
        var outputTask = Task.Run(() => process!.StandardOutput.ReadToEnd());
        var errorTask = Task.Run(() => process!.StandardError.ReadToEnd());
        process!.WaitForExit();
        var output = outputTask.Result;
        var error = errorTask.Result;
```

The full `Run` method after the edit:

```csharp
    public static CommandResult Run(string command, string args)
    {
        var psi = new ProcessStartInfo
        {
            FileName = command,
            Arguments = args,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };

        using var process = Process.Start(psi);
        var outputTask = Task.Run(() => process!.StandardOutput.ReadToEnd());
        var errorTask = Task.Run(() => process!.StandardError.ReadToEnd());
        process!.WaitForExit();
        var output = outputTask.Result;
        var error = errorTask.Result;

        return new CommandResult(process.ExitCode, output, error);
    }
```

**Step 2: Verify the library compiles**

Run: `dotnet build scripts/lib/StackLib.csproj`
Expected: Build succeeded with 0 errors.

**Step 3: Commit**

```bash
git add scripts/lib/ProcessRunner.cs
git commit -m "fix: prevent deadlock in ProcessRunner.Run with concurrent stream reads"
```

---

### Task 2: Fix deadlock in ProcessRunner.RunInDir

**Files:**
- Modify: `scripts/lib/ProcessRunner.cs:43-79` (the `RunInDir` method)

**Context:** Same deadlock pattern as `Run`. Same fix: read stdout and stderr concurrently.

**Step 1: Fix the concurrent read in `RunInDir`**

Replace lines 68-71 in `scripts/lib/ProcessRunner.cs`:

```csharp
        // OLD:
        // using var process = Process.Start(psi);
        // var output = process!.StandardOutput.ReadToEnd();
        // var error = process.StandardError.ReadToEnd();
        // process.WaitForExit();

        // NEW:
        using var process = Process.Start(psi);
        var outputTask = Task.Run(() => process!.StandardOutput.ReadToEnd());
        var errorTask = Task.Run(() => process!.StandardError.ReadToEnd());
        process!.WaitForExit();
        var output = outputTask.Result;
        var error = errorTask.Result;
```

The full `RunInDir` method after the edit:

```csharp
    public static CommandResult RunInDir(
        string command,
        string args,
        string workingDir,
        Dictionary<string, string>? envVars = null,
        bool printErrors = true)
    {
        var psi = new ProcessStartInfo
        {
            FileName = command,
            Arguments = args,
            WorkingDirectory = workingDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };

        if (envVars != null)
        {
            foreach (var env in envVars)
            {
                psi.Environment[env.Key] = env.Value;
            }
        }

        using var process = Process.Start(psi);
        var outputTask = Task.Run(() => process!.StandardOutput.ReadToEnd());
        var errorTask = Task.Run(() => process!.StandardError.ReadToEnd());
        process!.WaitForExit();
        var output = outputTask.Result;
        var error = errorTask.Result;

        if (printErrors && !string.IsNullOrEmpty(error) && process.ExitCode != 0)
        {
            Console.WriteLine(error);
        }

        return new CommandResult(process.ExitCode, output, error);
    }
```

**Step 2: Verify the library compiles**

Run: `dotnet build scripts/lib/StackLib.csproj`
Expected: Build succeeded with 0 errors.

**Step 3: Commit**

```bash
git add scripts/lib/ProcessRunner.cs
git commit -m "fix: prevent deadlock in ProcessRunner.RunInDir with concurrent stream reads"
```

---

### Task 3: Add RunStreaming method to ProcessRunner

**Files:**
- Modify: `scripts/lib/ProcessRunner.cs` (add new method after `RunInDir`, before the closing `}` of the class)

**Context:** This method streams docker output to the console in real-time so users see progress. It uses `BeginOutputReadLine`/`BeginErrorReadLine` with event handlers. It captures output in StringBuilders for the return value. It supports a timeout to kill hung processes.

**Step 1: Add the RunStreaming method**

Add this method after the `RunInDir` method (after its closing `}`, before the class closing `}`):

```csharp
    /// <summary>
    /// Run a command with real-time output streaming and timeout support.
    /// Output lines are printed to console with indentation as they arrive.
    /// </summary>
    public static CommandResult RunStreaming(
        string command,
        string args,
        string workingDir,
        Dictionary<string, string>? envVars = null,
        int timeoutSeconds = 300)
    {
        var psi = new ProcessStartInfo
        {
            FileName = command,
            Arguments = args,
            WorkingDirectory = workingDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };

        if (envVars != null)
        {
            foreach (var env in envVars)
            {
                psi.Environment[env.Key] = env.Value;
            }
        }

        var outputBuilder = new System.Text.StringBuilder();
        var errorBuilder = new System.Text.StringBuilder();

        using var process = Process.Start(psi);

        process!.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null)
            {
                outputBuilder.AppendLine(e.Data);
                if (!string.IsNullOrWhiteSpace(e.Data))
                    Console.WriteLine($"  {e.Data}");
            }
        };

        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null)
            {
                errorBuilder.AppendLine(e.Data);
                if (!string.IsNullOrWhiteSpace(e.Data))
                    Console.WriteLine($"  {e.Data}");
            }
        };

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        var exited = process.WaitForExit(timeoutSeconds * 1000);

        if (!exited)
        {
            try { process.Kill(entireProcessTree: true); } catch { }
            return new CommandResult(-1, outputBuilder.ToString(), "Process timed out");
        }

        // Ensure async event handlers have flushed
        process.WaitForExit();

        return new CommandResult(process.ExitCode, outputBuilder.ToString(), errorBuilder.ToString());
    }
```

**Step 2: Verify the library compiles**

Run: `dotnet build scripts/lib/StackLib.csproj`
Expected: Build succeeded with 0 errors.

**Step 3: Commit**

```bash
git add scripts/lib/ProcessRunner.cs
git commit -m "feat: add RunStreaming method with real-time output and timeout support"
```

---

### Task 4: Update start.cs to use RunStreaming

**Files:**
- Modify: `scripts/start.cs:38` (change `RunInDir` call to `RunStreaming`)

**Context:** The start script runs `docker compose up -d` for each service. This is the main place where the hang occurs because docker compose writes pull/create/start progress to stderr. Switch to `RunStreaming` so users see progress.

**Step 1: Replace RunInDir with RunStreaming in start.cs**

Change line 38 from:

```csharp
    var result = ProcessRunner.RunInDir("docker", composeArgs, service.ServiceDir, envVars);
```

To:

```csharp
    var result = ProcessRunner.RunStreaming("docker", composeArgs, service.ServiceDir, envVars);
```

**Step 2: Update the failure message to handle timeouts**

Change lines 44-47 from:

```csharp
    else
    {
        Console.WriteLine($"✗ {service.Name} - failed");
    }
```

To:

```csharp
    else
    {
        var reason = result.Error == "Process timed out" ? "timed out" : "failed";
        Console.WriteLine($"✗ {service.Name} - {reason}");
    }
```

**Step 3: Verify the script compiles**

Run: `dotnet build scripts/start.cs`
Expected: Build succeeded (AOT warning IL3050 is expected and can be ignored).

**Step 4: Commit**

```bash
git add scripts/start.cs
git commit -m "feat: stream docker output in start script for progress visibility"
```

---

### Task 5: Update update.cs to use RunStreaming

**Files:**
- Modify: `scripts/update.cs:84,89,94` (three `RunInDir` calls to `RunStreaming`)

**Context:** The update script has three docker compose calls per service: `build --pull` OR `pull`, then `up -d`. All three can hang and should stream output. The status detection logic (`result.Error.Contains("Recreat")`) still works because `RunStreaming` captures stderr in the return value.

**Step 1: Replace the three RunInDir calls with RunStreaming**

Change line 84 from:

```csharp
        ProcessRunner.RunInDir("docker", composeArgs + " build --pull", service.ServiceDir, envVars);
```

To:

```csharp
        ProcessRunner.RunStreaming("docker", composeArgs + " build --pull", service.ServiceDir, envVars);
```

Change line 89 from:

```csharp
        ProcessRunner.RunInDir("docker", composeArgs + " pull", service.ServiceDir, envVars);
```

To:

```csharp
        ProcessRunner.RunStreaming("docker", composeArgs + " pull", service.ServiceDir, envVars);
```

Change line 94 from:

```csharp
    var result = ProcessRunner.RunInDir("docker", composeArgs + upArgs, service.ServiceDir, envVars);
```

To:

```csharp
    var result = ProcessRunner.RunStreaming("docker", composeArgs + upArgs, service.ServiceDir, envVars);
```

**Step 2: Update the failure message to handle timeouts**

Change lines 103-105 from:

```csharp
    else
    {
        Console.WriteLine($"✗ {service.Name} - failed");
    }
```

To:

```csharp
    else
    {
        var reason = result.Error == "Process timed out" ? "timed out" : "failed";
        Console.WriteLine($"✗ {service.Name} - {reason}");
    }
```

**Step 3: Verify the script compiles**

Run: `dotnet build scripts/update.cs`
Expected: Build succeeded (AOT warning IL3050 is expected and can be ignored).

**Step 4: Commit**

```bash
git add scripts/update.cs
git commit -m "feat: stream docker output in update script for progress visibility"
```

---

### Task 6: Manual smoke test

**Context:** These scripts orchestrate docker compose, so automated unit tests aren't practical. Verify manually.

**Step 1: Test start.cs**

Run: `dotnet run scripts/start.cs`

Expected behavior:
- Each service prints "Starting <name>..."
- Docker compose output streams in real-time with `  ` indent (e.g., `  Container stack-postgres-1  Started`)
- Each service shows success/failure after docker finishes
- Script does NOT hang

**Step 2: Test stop.cs**

Run: `dotnet run scripts/stop.cs`

Expected behavior:
- Services stop without hanging (deadlock fix in `RunInDir` applies here too)

**Step 3: Test update.cs**

Run: `dotnet run scripts/update.cs`

Expected behavior:
- Pull/build progress streams in real-time
- Up status streams in real-time
- Shows (recreated) or (no changes) per service
- Script does NOT hang

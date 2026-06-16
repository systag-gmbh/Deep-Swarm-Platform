# Claude Code Guidelines

**IMPORTANT: Use [Conventional Commits](https://www.conventionalcommits.org/) for all git commit messages.**

Examples: `feat: add user auth`, `fix: resolve login bug`, `docs: update README`, `refactor: simplify config loader`

## Project Overview

This is a modular Docker Compose stack with .NET 10 file-based orchestration scripts.

## Directory Structure

```
/workspaces/src/
├── scripts/           # .NET 10 file-based scripts
│   └── lib/           # Shared library (StackLib)
├── services/          # Docker Compose service definitions (NN-name pattern)
├── overrides/         # Service override files
├── stack.json         # Base configuration
├── stack.local.json   # User overrides (gitignored)
├── landing.yaml.example  # Landing page template
├── landing.yaml          # User landing config (gitignored)
└── .env                  # Environment variables (gitignored)
```

## .NET 10 File-Based Scripts

### Shebang Line

Use `-S` flag to pass arguments:

```csharp
#!/usr/bin/env -S dotnet run
```

### Shared Library (scripts/lib/)

Scripts use a shared library (`StackLib`) to avoid code duplication. Reference it with `#:project`:

```csharp
#!/usr/bin/env -S dotnet run
#:project lib/StackLib.csproj

using StackLib;

var config = ConfigLoader.LoadConfig(Environment.CurrentDirectory);
```

**Library classes:**
- `ConfigLoader` - Load stack.json/stack.local.json, .env files
- `ProcessRunner` - Execute external commands (Run, RunInDir)
- `DockerHelpers` - Docker network and compose utilities
- `ServiceManager` - Iterate services in order (ascending/descending)

### Package References

Add NuGet packages with `#:package` directive:

```csharp
#:package YamlDotNet@16.3.0
#:package Newtonsoft.Json@13.0.4
```

### Path Resolution

**Important:** `AppContext.BaseDirectory` returns a temp compilation directory, not the script location.

```csharp
// WRONG - points to temp directory
var scriptDir = Path.GetDirectoryName(AppContext.BaseDirectory);

// CORRECT - use working directory
var repoRoot = Environment.CurrentDirectory;
```

### Code Structure

Top-level statements must come before class/type declarations:

```csharp
#!/usr/bin/env -S dotnet run
#:package YamlDotNet@16.3.0

using System;

// 1. Top-level code first
var config = LoadConfig();
Console.WriteLine("Done");

// 2. Static local functions
static Config LoadConfig() { ... }

// 3. Classes/records last
class Config { ... }
```

### Running Scripts

```bash
# From repo root
dotnet run scripts/script-name.cs

# Or make executable and run directly
chmod +x scripts/script-name.cs
./scripts/script-name.cs
```

### AOT Warning

This warning can be ignored for file-based scripts:
```
warning IL3050: Using member '...' which has 'RequiresDynamicCodeAttribute'
```

## Landing Page Generation

Copy `landing.yaml.example` to `landing.yaml` if it doesn't exist, then edit to change services/ports. **After modifying `landing.yaml`, regenerate the landing page:**

```bash
cp landing.yaml.example landing.yaml  # First time only
dotnet run scripts/generate-landing.cs
```

## Service Naming Convention

Services use numeric prefixes for ordering:
- `00-*` - Infrastructure (backup)
- `10-*` - Core (database, object storage)
- `20-*` - Applications (caddy, n8n, appsmith, etc.)

## Adding New Services

When adding a new service, update ALL of these files (see [README.md](README.md#adding-new-services) for details):

1. **Create service directory:** `services/NN-name/docker-compose.yml`
2. **stack.json:** Add service to the services array
3. **landing.yaml:** Add link to landing page (both `landing.yaml` and `landing.yaml.example`)
4. **Caddyfile:** Add reverse proxy entry (both `Caddyfile` and `Caddyfile.example`)
5. **Caddy override:** Add port mapping (both `.yml` and `.yml.example`)
6. **README.md:** Update services table, network diagram, directory structure
7. **.env.example:** Add any new environment variables or notes
8. **Regenerate landing page:** `dotnet run scripts/generate-landing.cs`

**Important:** Always update both the active config files AND their `.example` counterparts to keep them in sync.

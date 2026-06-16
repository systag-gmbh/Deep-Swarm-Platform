# Versioning Design

## Overview

Add version display to the landing page showing semantic version, git commit hash, and build timestamp.

## Display Format

```
v1.0.0 (abc1234) • Built 21.01.26 14:30
```

Components:
- `v1.0.0` - Semantic version from `VERSION` file
- `abc1234` - Short git commit hash (7 chars)
- `21.01.26 14:30` - Local server time, German date format (dd.MM.yy HH:mm)

## Components

### VERSION File

Location: Repository root (`VERSION`)

Format: Single line containing semantic version number (no `v` prefix)

```
1.0.0
```

Initial version: `1.0.0`

### Release Script

Location: `scripts/release.cs`

**Usage:**
```bash
./scripts/release.cs 1.1.0    # Create release v1.1.0
./scripts/release.cs          # Show current version
```

**Behavior:**
1. Validates version format (must be semver: X.Y.Z)
2. Checks working directory is clean (no uncommitted changes)
3. Updates VERSION file
4. Commits with message `chore: release v1.1.0`
5. Creates git tag `v1.1.0`
6. Prints next steps (manual push)

### Landing Page Changes

**YAML schema** - Add optional `showVersion` flag to groups:

```yaml
groups:
  - name: "Deep Swarm Plattform"
    showVersion: true
    links:
      - name: "n8n"
        # ...
```

**HTML output** (inside card, after `.links` div):

```html
<div class="version">v1.0.0 (abc1234) • Built 21.01.26 14:30</div>
```

**CSS:**

```css
.card .version {
    margin-top: 1rem;
    padding-top: 0.75rem;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    color: #64748b;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-align: center;
}
```

## Files

**Create:**
- `VERSION` - Initial version `1.0.0`
- `scripts/release.cs` - Release helper script

**Modify:**
- `scripts/generate-landing.cs` - Read version, commit, timestamp; inject into cards with `showVersion: true`
- `landing.yaml.example` - Add `showVersion: true` example
- `README.md` - Add "Creating Releases" documentation section

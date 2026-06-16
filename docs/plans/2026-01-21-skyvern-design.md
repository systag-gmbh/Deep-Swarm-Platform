# Skyvern Service Design

**Date:** 2026-01-21
**Status:** Approved

## Overview

Add Skyvern AI browser automation to the Docker stack. Skyvern uses LLM-powered agents to automate web browser interactions.

## Architecture

**Service name:** `20-skyvern`

**Components:**
- `skyvern` - Backend API server (Python/FastAPI)
- `skyvern-ui` - Frontend React app

**Network topology:**
```
                    Internet
                        │
                        ▼ :8089
                ┌───────────────┐
                │     Caddy     │
                │  (with auth)  │
                └───────┬───────┘
                        │ proxy network
                        ▼
                ┌───────────────┐
                │  skyvern-ui   │──────► skyvern:8000 (API)
                └───────────────┘
                                              │
        ┌─────────────────────────────────────┤ ai-internal network
        │                                     │
        ▼                                     ▼
    ┌───────┐                          ┌───────────┐
    │  n8n  │ ─────────────────────►   │  skyvern  │
    └───────┘   http://skyvern:8000    └─────┬─────┘
                                             │
              ┌──────────────────────────────┤
              │ database network             │ proxy network (to litellm)
              ▼                              ▼
        ┌──────────┐                  ┌───────────┐
        │ postgres │                  │  litellm  │
        └──────────┘                  └───────────┘
```

**Access:**
- External: UI on port 8089 with Caddy authentication
- Internal: API available to n8n via `ai-internal` network at `http://skyvern:8000`

**LLM:** Routes through LiteLLM using OpenAI-compatible API with model `openai/gpt-5.2`

**Data storage:** `${DATA_PATH}/skyvern/` with subdirectories:
- `artifacts/` - Screenshots and other artifacts
- `videos/` - Browser session recordings
- `har/` - HTTP archive files
- `log/` - Application logs
- `streamlit/` - Streamlit configuration

## Implementation

### 1. Create Service Definition

**File:** `services/20-skyvern/docker-compose.yml`

```yaml
services:
  skyvern:
    image: skyvern/skyvern:v1.0.9
    hostname: skyvern
    restart: unless-stopped
    volumes:
      - ${DATA_PATH}/skyvern/artifacts:/data/artifacts
      - ${DATA_PATH}/skyvern/videos:/data/videos
      - ${DATA_PATH}/skyvern/har:/data/har
      - ${DATA_PATH}/skyvern/log:/data/log
      - ${DATA_PATH}/skyvern/streamlit:/app/.streamlit
    environment:
      - DATABASE_STRING=postgresql+psycopg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@postgres:5432/skyvern
      - BROWSER_TYPE=chromium-headful
      - ENABLE_OPENAI_COMPATIBLE=true
      - LLM_KEY=OPENAI_COMPATIBLE
      - OPENAI_COMPATIBLE_MODEL_NAME=${SKYVERN_LLM_MODEL:-openai/gpt-5.2}
      - OPENAI_COMPATIBLE_API_KEY=${SKYVERN_LLM_API_KEY}
      - OPENAI_COMPATIBLE_API_BASE=http://litellm:4000/v1
      - ENABLE_CODE_BLOCK=true
      - ENABLE_LOG_ARTIFACTS=${SKYVERN_ENABLE_LOG_ARTIFACTS:-false}
      - SKYVERN_TELEMETRY=false
    networks:
      - database
      - proxy
      - ai-internal
    healthcheck:
      test: ["CMD", "test", "-f", "/app/.streamlit/secrets.toml"]
      interval: 5s
      timeout: 5s
      retries: 5

  skyvern-ui:
    image: skyvern/skyvern-ui:v1.0.9
    hostname: skyvern-ui
    restart: unless-stopped
    entrypoint: ["npm", "run", "start"]
    volumes:
      - ${DATA_PATH}/skyvern/artifacts:/data/artifacts
      - ${DATA_PATH}/skyvern/videos:/data/videos
      - ${DATA_PATH}/skyvern/har:/data/har
    environment:
      - VITE_API_BASE_URL=https://${SKYVERN_HOST:-localhost}:8089/api/v1
      - VITE_ARTIFACT_API_BASE_URL=https://${SKYVERN_HOST:-localhost}:8089
      - VITE_WSS_BASE_URL=wss://${SKYVERN_HOST:-localhost}:8089/api/v1
      - VITE_SKYVERN_API_KEY=${SKYVERN_API_KEY}
      - VITE_ENABLE_LOG_ARTIFACTS=${SKYVERN_ENABLE_LOG_ARTIFACTS:-false}
      - VITE_ENABLE_CODE_BLOCK=true
    networks:
      - proxy
    depends_on:
      skyvern:
        condition: service_healthy

networks:
  proxy:
    name: ${PROJECT_NAME}_proxy
    external: true
  database:
    name: ${PROJECT_NAME}_database
    external: true
  ai-internal:
    name: ${PROJECT_NAME}_ai-internal
    external: true
```

### 2. Update Database Init

**File:** `services/10-postgres/init/01-databases.sql`

Add line:
```sql
CREATE DATABASE skyvern;
```

### 3. Update Caddy Configuration

**File:** `services/90-caddy/Caddyfile` (and `Caddyfile.example`)

Add block:
```
:8089 {
    tls internal

    # All routes require authentication
    authorize with default_policy

    # API and WebSocket routes (required for UI functionality)
    @backend path /api/* /artifact/* /v1/*
    handle @backend {
        reverse_proxy skyvern:8000
    }

    # UI static files
    handle {
        reverse_proxy skyvern-ui:8080
    }
}
```

**File:** `overrides/90-caddy.override.yml` (and `.example`)

Add to ports:
```yaml
- "8089:8089"
```

### 4. Update Environment Template

**File:** `.env.example`

Add section:
```bash
# =============================================================================
# SKYVERN CONFIGURATION
# =============================================================================
# Host for Skyvern UI (used for WebSocket and API URLs)
SKYVERN_HOST=localhost

# LLM model to use (must be configured in LiteLLM)
SKYVERN_LLM_MODEL=openai/gpt-5.2

# LiteLLM API key (your LiteLLM master key)
SKYVERN_LLM_API_KEY=

# API key for Skyvern (generated on first run, or set manually)
SKYVERN_API_KEY=

# Enable saving logs as artifacts (useful for debugging)
SKYVERN_ENABLE_LOG_ARTIFACTS=false
```

### 5. Update Stack Configuration

**File:** `stack.json`

Add `"20-skyvern"` to services array.

### 6. Update Landing Page

**File:** `landing.yaml` (and `landing.yaml.example`)

Add entry:
```yaml
- name: "Skyvern"
  url: "https://localhost:8089"
  icon: "robot"
  description: "AI Browser Automation"
```

### 7. Update Documentation

**File:** `README.md`

- Add Skyvern to services table (port 8089)
- Update network diagram to include Skyvern
- Add to directory structure

## Post-Implementation Steps

```bash
# If postgres is already running, create database manually
docker exec -it stack-postgres-1 psql -U postgres -c "CREATE DATABASE skyvern;"

# Regenerate landing page
./scripts/generate-landing.cs

# Start/restart stack
./scripts/start.cs
```

## Files Changed

| File | Action |
|------|--------|
| `services/20-skyvern/docker-compose.yml` | Create |
| `services/10-postgres/init/01-databases.sql` | Update |
| `services/90-caddy/Caddyfile` | Update |
| `services/90-caddy/Caddyfile.example` | Update |
| `overrides/90-caddy.override.yml` | Update |
| `overrides/90-caddy.override.yml.example` | Update |
| `.env.example` | Update |
| `stack.json` | Update |
| `landing.yaml` | Update |
| `landing.yaml.example` | Update |
| `README.md` | Update |

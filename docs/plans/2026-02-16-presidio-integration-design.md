# Presidio PII Analyzer Integration Design

## Overview

Integrate the PII analyzer/guardrail and frontend from `examples/systag-litellm/` into the main stack as a first-class service. This adds ensemble NER-based PII detection (NerGuard-0.3B + GLiNER), an interactive testing UI, and optional per-request PII masking/deanonymizing for all LLM calls through LiteLLM.

## Components

1. **Presidio Analyzer** (Flask API) - PII detection and anonymization using ensemble NER
2. **GLiNER Server** (Rust/ONNX sidecar) - span-based NER inference
3. **PII Analyzer Frontend** (React/Vite SPA) - interactive testing UI served as static files by Caddy
4. **LiteLLM PII Guardrail** - pre/post call hooks that mask/unmask PII transparently, per-request opt-in

## Directory Structure

```
services/15-presidio/
├── docker-compose.yml          # presidio-analyzer + gliner + frontend-build
├── Dockerfile.analyzer         # Python 3.13 + Presidio + NerGuard
├── Dockerfile.gliner           # Multi-stage: ONNX export → Rust compile → runtime
├── Dockerfile.frontend         # Multi-stage: Node build → busybox copy to volume
├── analyzer/                   # Flask API source (copied from example)
├── gliner-server/              # Rust gline-rs source (copied from example)
└── frontend/                   # React/Vite SPA source (copied from example)

services/20-litellm/
├── docker-compose.yml          # Modified: add config volume, entrypoint, env vars
└── litellm-config/
    ├── config.yaml             # Guardrail-only config (models stay in DB)
    └── pii_guardrail.py        # Custom guardrail (pre/post hooks)
```

## Docker Compose: `services/15-presidio/docker-compose.yml`

### presidio-analyzer

- **Image:** Custom build from `Dockerfile.analyzer`
- **Networks:** `proxy` (for Caddy), `ai-internal` (for LiteLLM)
- **Volumes:** `${DATA_PATH}/presidio/model-cache:/app/model-cache`, shared `pii_cache` volume
- **Health check:** `curl http://localhost:5002/health`, 120s start period (model loading)
- **Memory limit:** 4GB
- **Depends on:** gliner (healthy)
- **Environment:** Configurable via `.env` (score threshold, excluded entities, audit logging)

### gliner

- **Image:** Custom build from `Dockerfile.gliner`
- **Networks:** `ai-internal` only
- **Health check:** `curl http://localhost:5003/health`, 60s start period
- **Memory limit:** 2GB
- **No ports exposed** (internal sidecar)

### pii-analyzer-frontend

- **Image:** Custom build from `Dockerfile.frontend` (multi-stage: Node builds, busybox copies)
- **Volumes:** `${DATA_PATH}/presidio/frontend-dist:/output`
- **One-shot container:** Copies built static files to DATA_PATH, then exits
- **restart: "no"**

## LiteLLM Integration

### Modified `services/20-litellm/docker-compose.yml`

- Add `entrypoint: ["sh", "-c"]` and `command: ["pip install diskcache && litellm --config=/app/config/config.yaml"]`
- Add volume mounts: `./litellm-config:/app/config:ro` and shared `pii_cache` volume
- Add environment: `PRESIDIO_ANALYZER_API_BASE=http://presidio-analyzer:5002`, `ONNXRUNTIME_LOG_SEVERITY_LEVEL=3`

### Guardrail config (`litellm-config/config.yaml`)

- `default_on: false` for both `pii-mask` and `pii-unmask` guardrails
- Per-request opt-in: clients send `guardrails: ["pii-mask", "pii-unmask"]` in request metadata
- Models managed via DB (`store_model_in_db: true`), config only defines guardrails

### Shared state

- `pii_cache` named Docker volume shared between presidio-analyzer and LiteLLM
- Used by DiskCache for entity mappings (5min TTL) and message cache (1h TTL)

## Frontend & Caddy

### Caddy port 8090

Single port serves both the UI and proxies API calls to the analyzer:

- `@api` paths (`/analyze`, `/anonymize`, `/deanonymize`, `/health`, `/supportedentities`, `/recognizers`, `/anonymize_conversation`, `/cache_response`) → `reverse_proxy presidio-analyzer:5002`
- All other paths → static file server from `/srv/pii-analyzer` with SPA fallback (`try_files {path} /index.html`)
- Protected with `authorize with protected_policy`

### Caddy changes

- **Caddyfile + Caddyfile.example:** Add port 8090 block
- **overrides/90-caddy.override.yml + .example:** Add `"8090:8090"` port mapping and `${DATA_PATH}/presidio/frontend-dist:/srv/pii-analyzer:ro` volume mount

### Frontend code change

- Default `ANALYZER_BASE` changed from `"http://localhost:5002"` to `""` (empty string = relative URLs = same origin through Caddy)

## Network Topology

```
                    Caddy (proxy network)
                    :8090
                      │
              ┌───────┴───────┐
              │ static files  │ API proxy
              │ (frontend)    │
              │               ▼
              │     presidio-analyzer
              │     (proxy + ai-internal)
              │           │
              │           │ (ai-internal)
              │           ▼
              │        gliner
              │     (ai-internal)
              │
              │     LiteLLM :4000
              │     (proxy + database + ai-internal)
              │           │
              │           │ guardrail calls (ai-internal)
              │           ▼
              │     presidio-analyzer
              │           │
              │           ▼
              │        gliner
```

## Stack Configuration Changes

### stack.json

Add `"15-presidio"` between `"11-garage"` and `"20-appsmith"`.

### .env.example

Add section for Presidio configuration:
- `PRESIDIO_SCORE_THRESHOLD=0.5`
- `PRESIDIO_EXCLUDED_ENTITIES=DATE_TIME,AGE,GENDER`
- `PRESIDIO_AUDIT_LOGGING=false`

### landing.yaml.example

Add PII Analyzer entry on port 8090.

### overrides/90-caddy.override.yml + .example

Add port 8090 and frontend-dist volume mount.

## Update Flow

No changes needed to `update.cs` or `start.cs`. Existing logic handles everything:

1. `git pull` brings new source
2. `15-presidio` has Dockerfiles → `docker compose build --pull` rebuilds changed images
3. `docker compose up -d` → analyzer + gliner restart, frontend one-shot copies fresh dist
4. `20-litellm` → config volume mount picks up guardrail changes on restart
5. `90-caddy` → serves new frontend files immediately (volume mount)

Service ordering ensures `15-presidio` starts before `20-litellm` (which depends on it) and `90-caddy`.

## Resource Requirements

| Component | Memory | Startup |
|-----------|--------|---------|
| presidio-analyzer | 4GB | ~120s (model loading) |
| gliner | 2GB | ~60s |
| pii-analyzer-frontend | minimal | one-shot (exits) |
| **Total new** | **~6GB** | **~3min** |

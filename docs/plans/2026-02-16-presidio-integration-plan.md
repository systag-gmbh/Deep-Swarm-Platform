# Presidio PII Analyzer Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate the PII analyzer, GLiNER sidecar, frontend UI, and LiteLLM guardrail from `examples/systag-litellm/` into the main Docker Compose stack.

**Architecture:** New `services/15-presidio/` contains the analyzer, GLiNER, and frontend source+Dockerfiles. LiteLLM gets guardrail config in `services/20-litellm/litellm-config/`. Caddy serves the frontend on port 8090 and proxies API calls to the analyzer. The PII guardrail is per-request opt-in.

**Tech Stack:** Python 3.13 (Flask, Presidio, transformers), Rust (gline-rs, ONNX Runtime), React 19 + Vite 7, Docker Compose, Caddy

**Design doc:** `docs/plans/2026-02-16-presidio-integration-design.md`

---

### Task 1: Create `services/15-presidio/` and copy source from example

**Files:**
- Create: `services/15-presidio/` directory
- Copy: `examples/systag-litellm/analyzer/` → `services/15-presidio/analyzer/`
- Copy: `examples/systag-litellm/gliner-server/` → `services/15-presidio/gliner-server/`
- Copy: `examples/systag-litellm/frontend/` → `services/15-presidio/frontend/`
- Copy: `examples/systag-litellm/Dockerfile.analyzer` → `services/15-presidio/Dockerfile.analyzer`
- Copy: `examples/systag-litellm/Dockerfile.gliner` → `services/15-presidio/Dockerfile.gliner`

**Step 1: Create directory and copy source**

```bash
mkdir -p services/15-presidio
cp -r examples/systag-litellm/analyzer services/15-presidio/
cp -r examples/systag-litellm/gliner-server services/15-presidio/
cp -r examples/systag-litellm/frontend services/15-presidio/
cp examples/systag-litellm/Dockerfile.analyzer services/15-presidio/
cp examples/systag-litellm/Dockerfile.gliner services/15-presidio/
```

**Step 2: Remove dev artifacts from copied frontend**

```bash
rm -rf services/15-presidio/frontend/node_modules services/15-presidio/frontend/dist
```

**Step 3: Verify file structure**

```bash
find services/15-presidio -type f | head -30
```

Expected: Files in `analyzer/`, `gliner-server/`, `frontend/`, plus two Dockerfiles.

**Step 4: Commit**

```bash
git add services/15-presidio/
git commit -m "feat: add 15-presidio service with analyzer, gliner, and frontend source"
```

---

### Task 2: Update frontend default API base URL

**Files:**
- Modify: `services/15-presidio/frontend/src/App.jsx:4`

**Step 1: Change ANALYZER_BASE constant**

In `services/15-presidio/frontend/src/App.jsx`, line 4, change:

```javascript
const ANALYZER_BASE = "http://localhost:5002";
```

to:

```javascript
const ANALYZER_BASE = "";
```

This makes API calls use relative URLs (same origin through Caddy on port 8090).

**Step 2: Commit**

```bash
git add services/15-presidio/frontend/src/App.jsx
git commit -m "feat: change frontend API base to relative URL for Caddy integration"
```

---

### Task 3: Create `Dockerfile.frontend`

**Files:**
- Create: `services/15-presidio/Dockerfile.frontend`

**Step 1: Write the Dockerfile**

```dockerfile
# Multi-stage build: Node builds frontend, busybox copies dist to volume
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM busybox:1.37
COPY --from=build /app/dist /dist
CMD ["cp", "-r", "/dist/.", "/output/"]
```

**Step 2: Commit**

```bash
git add services/15-presidio/Dockerfile.frontend
git commit -m "feat: add frontend Dockerfile for static build"
```

---

### Task 4: Create `services/15-presidio/docker-compose.yml`

**Files:**
- Create: `services/15-presidio/docker-compose.yml`

**Step 1: Write docker-compose.yml**

```yaml
services:
  presidio-analyzer:
    build:
      context: .
      dockerfile: Dockerfile.analyzer
    image: presidio-analyzer-nerguard:latest
    hostname: presidio-analyzer
    environment:
      TRANSFORMERS_VERBOSITY: "error"
      TOKENIZERS_PARALLELISM: "false"
      USE_GPU: "false"
      HF_HUB_DISABLE_TELEMETRY: "1"
      HF_HOME: /app/model-cache
      TRANSFORMERS_CACHE: /app/model-cache
      GLINER_URL: "http://gliner:5003"
      PORT: "5002"
      SCORE_THRESHOLD: "${PRESIDIO_SCORE_THRESHOLD:-0.5}"
      EXCLUDED_ENTITIES: "${PRESIDIO_EXCLUDED_ENTITIES:-DATE_TIME,AGE,GENDER}"
      AUDIT_LOGGING: "${PRESIDIO_AUDIT_LOGGING:-false}"
    volumes:
      - ${DATA_PATH}/presidio/model-cache:/app/model-cache
      - pii_cache:/tmp/pii_cache
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5002/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
    depends_on:
      gliner:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 4G
    networks:
      - proxy
      - ai-internal
    restart: unless-stopped

  gliner:
    build:
      context: .
      dockerfile: Dockerfile.gliner
    image: gliner-server:latest
    hostname: gliner
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5003/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 2G
    networks:
      - ai-internal
    restart: unless-stopped

  pii-analyzer-frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    image: pii-analyzer-frontend:latest
    volumes:
      - ${DATA_PATH}/presidio/frontend-dist:/output
    restart: "no"

volumes:
  pii_cache:

networks:
  proxy:
    name: ${PROJECT_NAME}_proxy
    external: true
  ai-internal:
    name: ${PROJECT_NAME}_ai-internal
    external: true
```

**Step 2: Verify YAML is valid**

```bash
cd services/15-presidio && docker compose config --quiet; echo $?
```

Expected: `0` (valid YAML).

**Step 3: Commit**

```bash
git add services/15-presidio/docker-compose.yml
git commit -m "feat: add 15-presidio docker-compose with analyzer, gliner, and frontend-build"
```

---

### Task 5: Create LiteLLM guardrail config

**Files:**
- Create: `services/20-litellm/litellm-config/config.yaml`
- Create: `services/20-litellm/litellm-config/pii_guardrail.py`

**Step 1: Create directory**

```bash
mkdir -p services/20-litellm/litellm-config
```

**Step 2: Write `config.yaml`**

```yaml
# Guardrail-only config — models are managed via database (STORE_MODEL_IN_DB=True)
# PII guardrail is per-request opt-in (default_on: false)
# Clients activate by sending: guardrails: ["pii-mask", "pii-unmask"] in request metadata

guardrails:
  - guardrail_name: "pii-mask"
    litellm_params:
      guardrail: pii_guardrail.PiiGuardrail
      mode: "pre_call"
      default_on: false
  - guardrail_name: "pii-unmask"
    litellm_params:
      guardrail: pii_guardrail.PiiGuardrail
      mode: "post_call"
      default_on: false

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true
```

**Step 3: Copy `pii_guardrail.py` from example**

```bash
cp examples/systag-litellm/litellm-config/pii_guardrail.py services/20-litellm/litellm-config/
```

**Step 4: Commit**

```bash
git add services/20-litellm/litellm-config/
git commit -m "feat: add PII guardrail config for LiteLLM (per-request opt-in)"
```

---

### Task 6: Modify `services/20-litellm/docker-compose.yml`

**Files:**
- Modify: `services/20-litellm/docker-compose.yml`

**Step 1: Update docker-compose.yml**

Replace the full contents with:

```yaml
services:
  litellm:
    image: ghcr.io/berriai/litellm:v1.80.8-stable
    hostname: litellm
    entrypoint: ["sh", "-c"]
    command: ["pip install diskcache && litellm --config=/app/config/config.yaml"]
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@postgres:5432/${LITELLM_DB:-litellm}
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
      PROXY_BASE_URL: ${LITELLM_PROXY_BASE_URL:-https://localhost:8083}
      STORE_MODEL_IN_DB: "True"
      PRESIDIO_ANALYZER_API_BASE: "http://presidio-analyzer:5002"
      ONNXRUNTIME_LOG_SEVERITY_LEVEL: "3"
    volumes:
      - ./litellm-config:/app/config:ro
      - pii_cache:/tmp/pii_cache
    networks:
      - proxy
      - database
      - ai-internal
    restart: unless-stopped

volumes:
  pii_cache:

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

Changes from original:
- Added `entrypoint` + `command` to install diskcache and load config
- Added `PRESIDIO_ANALYZER_API_BASE` and `ONNXRUNTIME_LOG_SEVERITY_LEVEL` environment vars
- Added `volumes` for litellm-config mount and shared pii_cache
- Added `volumes` top-level section for pii_cache

**Step 2: Verify YAML is valid**

```bash
cd services/20-litellm && docker compose config --quiet; echo $?
```

Expected: `0`.

**Step 3: Commit**

```bash
git add services/20-litellm/docker-compose.yml
git commit -m "feat: add PII guardrail volumes and config to LiteLLM service"
```

---

### Task 7: Update `stack.json`

**Files:**
- Modify: `stack.json`

**Step 1: Add `15-presidio` to services array**

Insert `"15-presidio"` after `"11-garage"` and before `"20-appsmith"`:

```json
{
  "project_name": "stack",
  "data_path": "/docker/data",
  "backup_path": "/docker",
  "backup_output_path": "/backups",
  "networks": {
    "proxy": {},
    "database": {},
    "ai-internal": {}
  },
  "services": [
    "00-resticker",
    "10-postgres",
    "11-garage",
    "15-presidio",
    "20-appsmith",
    "20-dozzle",
    "20-litellm",
    "20-n8n",
    "20-pgadmin",
    "20-ragflow",
    "20-nextcloud",
    "20-skyvern",
    "90-caddy"
  ]
}
```

**Step 2: Commit**

```bash
git add stack.json
git commit -m "feat: add 15-presidio to stack services"
```

---

### Task 8: Update `.env.example`

**Files:**
- Modify: `.env.example`

**Step 1: Add Presidio section**

Add after the Caddy Security section and before the Skyvern section:

```bash
# ===================
# Presidio PII Analyzer
# ===================
PRESIDIO_SCORE_THRESHOLD=0.5
PRESIDIO_EXCLUDED_ENTITIES=DATE_TIME,AGE,GENDER
PRESIDIO_AUDIT_LOGGING=false
# DANGER: logs actual PII values (testing only!)
# PRESIDIO_DANGER_AUDIT_LOG_PII=false
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add Presidio environment variables to .env.example"
```

---

### Task 9: Update Caddyfile and Caddyfile.example

**Files:**
- Modify: `services/90-caddy/Caddyfile`
- Modify: `services/90-caddy/Caddyfile.example`

**Step 1: Add port 8090 block to `Caddyfile`**

Add before the commented-out public domain examples at the end:

```
# Port 8090 - PII Analyzer (protected)
https://deepswarm-agent-platform-dev.systag.cloud:8090 {
    authorize with protected_policy

    # API routes → presidio-analyzer
    @api {
        path /analyze /anonymize /deanonymize /health /supportedentities /recognizers /anonymize_conversation /cache_response
    }
    handle @api {
        reverse_proxy presidio-analyzer:5002
    }

    # Frontend static files (SPA fallback)
    handle {
        root * /srv/pii-analyzer
        try_files {path} /index.html
        file_server
    }
}
```

**Step 2: Add port 8090 block to `Caddyfile.example`**

Add the same block but with `localhost` and `tls internal`:

```
# Port 8090 - PII Analyzer (protected)
https://localhost:8090 {
    authorize with protected_policy

    # API routes → presidio-analyzer
    @api {
        path /analyze /anonymize /deanonymize /health /supportedentities /recognizers /anonymize_conversation /cache_response
    }
    handle @api {
        reverse_proxy presidio-analyzer:5002
    }

    # Frontend static files (SPA fallback)
    handle {
        root * /srv/pii-analyzer
        try_files {path} /index.html
        file_server
    }
    tls internal
}
```

**Step 3: Commit**

```bash
git add services/90-caddy/Caddyfile services/90-caddy/Caddyfile.example
git commit -m "feat: add PII Analyzer reverse proxy on port 8090 to Caddyfile"
```

---

### Task 10: Update Caddy override and docker-compose

**Files:**
- Modify: `overrides/90-caddy.override.yml`
- Modify: `overrides/90-caddy.override.yml.example`
- Modify: `services/90-caddy/docker-compose.yml`

**Step 1: Add port 8090 to override files**

Add `"8090:8090"` to the ports list in both `overrides/90-caddy.override.yml` and `overrides/90-caddy.override.yml.example`:

```yaml
services:
  caddy:
    ports:
      - "443:443"
      - "8080:8080"
      - "8081:8081"
      - "8082:8082"
      - "8083:8083"
      - "8084:8084"
      - "8085:8085"
      - "8086:8086"
      - "8087:8087"
      - "8088:8088"
      - "8089:8089"
      - "8090:8090"
    volumes:
      - ${DATA_PATH}/presidio/frontend-dist:/srv/pii-analyzer:ro
```

**Step 2: Commit**

```bash
git add overrides/90-caddy.override.yml overrides/90-caddy.override.yml.example services/90-caddy/docker-compose.yml
git commit -m "feat: add port 8090 and PII Analyzer frontend volume to Caddy"
```

---

### Task 11: Update `landing.yaml.example`

**Files:**
- Modify: `landing.yaml.example`

**Step 1: Add PII Analyzer entry**

Add after the Skyvern entry in the main group:

```yaml
      - name: "PII Analyzer"
        url: "https://localhost:8090"
        icon: "PII"
        description: "PII Erkennung & Anonymisierung"
```

**Step 2: Commit**

```bash
git add landing.yaml.example
git commit -m "docs: add PII Analyzer to landing page example"
```

---

### Task 12: Smoke test the integration

**Step 1: Verify all docker-compose files are valid**

```bash
cd services/15-presidio && docker compose config --quiet && echo "15-presidio: OK"
cd services/20-litellm && docker compose config --quiet && echo "20-litellm: OK"
cd services/90-caddy && docker compose config --quiet && echo "90-caddy: OK"
```

Expected: All three print "OK".

**Step 2: Verify stack.json has correct service count**

```bash
grep -c '"' stack.json | head -1
```

Verify 13 services listed (was 12, +1 for 15-presidio).

**Step 3: Verify Dockerfiles are detected by update script logic**

```bash
ls services/15-presidio/Dockerfile*
```

Expected: `Dockerfile.analyzer`, `Dockerfile.gliner`, `Dockerfile.frontend` — the update script's `HasDockerfile` check will find these.

**Step 4: Run analyzer unit tests (no running stack needed)**

```bash
cd services/15-presidio && python -m pytest analyzer/tests/ -v
```

Expected: All tests pass (these are the existing example tests, should work without modification).

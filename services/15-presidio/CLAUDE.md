# CLAUDE.md

## Project

Privacy data masking system using an ensemble of NerGuard-0.3B + GLiNER models via Microsoft Presidio.

## Architecture

3-container Docker stack:
- **Presidio Analyzer** (port 5002) — Ensemble NER + indexed anonymization + deanonymization
- **GLiNER sidecar** (port 5003) — ONNX-based span NER via Rust gline-rs server
- **Frontend** — React/Vite build-only container, outputs static files to volume

## Stack

Python 3.13 (container), Rust (gline-rs sidecar), React/Vite (frontend), Flask, Microsoft Presidio, NerGuard-0.3B (transformers), GLiNER (ONNX), Docker Compose

## Key Files

- `analyzer/startup.py` — Flask API: /analyze, /anonymize, /anonymize_conversation, /deanonymize, /cache_response, /health
- `analyzer/ensemble_recognizer.py` — Ensemble Presidio recognizer (NerGuard + GLiNER), merge logic, cross-type suppression, validation
- `analyzer/anonymize.py` — Indexed placeholder anonymization (overlap removal, right-to-left replacement)
- `analyzer/conversation.py` — Multi-turn anonymization with session-based DiskCache (registry + message cache)
- `analyzer/titles.py` — Title detection, stripping, and absorption into PERSON entities
- `frontend/src/App.jsx` — React SPA with entity highlighting, filtering, and masked/original views
- `gliner-server/` — Rust gline-rs sidecar (axum, ONNX Runtime)
- `docker-compose.yml` — Stack orchestration
- `Dockerfile.analyzer` — Python 3.13 container with Presidio + transformers
- `Dockerfile.gliner` — Multi-stage build: ONNX export → Rust compile → runtime
- `Dockerfile.frontend` — Node 22 Alpine build, outputs to volume

## Development

```bash
# Build and start the stack
docker compose up -d --build

# Run unit tests (no running stack needed)
cd analyzer && python -m pytest tests/ -v
```

## Key Design Decisions

- **Ensemble NER** — NerGuard-0.3B (token classification, in-process) + GLiNER (span-based, ONNX sidecar). Results merged with score boosting, cross-type containment suppression, and validation
- **Combined analyzer + anonymizer** in one container (no separate Presidio Anonymizer)
- **Indexed placeholders** (`<PERSON_1>`, `<PERSON_2>`) — same text (case-insensitive) gets same index
- **Two anonymization modes**: `/analyze` and `/anonymize` are fully stateless (no caching). `/anonymize_conversation` adds session-based DiskCache (1h TTL) with two caches: a **message cache** (skips NER for already-seen messages) and a **registry cache** (keeps placeholder indices stable across turns, e.g. "Robin Smith" stays `<PERSON_1>` in turn 2)
- **Title absorption** — titles (Dr., Prof., Mrs., etc.) are absorbed into adjacent PERSON entities to prevent information leakage
- **NerGuard model** loaded once at startup, cached in bind-mounted `model-cache` directory

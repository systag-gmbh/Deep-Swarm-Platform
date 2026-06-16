# Deep Swarm Agent Platform

A modular Docker Compose stack managed by .NET 10 file-based scripts.

[[_TOC_]]

## Quick Start

```bash
# Clone GIT Repository
# git clone ... directory

# Navigate to root folder of project
cd directory

# Configure environment
cp .env.example .env
# Edit .env with your settings (especially POSTGRES_PASSWORD)

# Configure enabled services
cp stack.json stack.local.json
# Edit stack.local.json to enable services

# Configure Caddy (required if using Caddy)
cp services/90-caddy/Caddyfile.example services/90-caddy/Caddyfile
# Edit Caddyfile to map ports to your services

# Configure Caddy ports (add the ports you need)
cp overrides/90-caddy.override.yml.example overrides/90-caddy.override.yml
# Edit to expose the HTTPS ports you configured in Caddyfile

# Configure authentication
# Set CADDY_JWT_SHARED_KEY in .env (generate with: openssl rand -hex 32)
dotnet run scripts/caddy-users.cs init
dotnet run scripts/caddy-users.cs add

# Build Caddy with security plugin
docker compose -f services/90-caddy/docker-compose.yml build

# Configure and generate landing page
cp landing.yaml.example landing.yaml
# Edit landing.yaml to customize your landing page
./scripts/generate-landing.cs

# Start
./scripts/start.cs
```

## Prerequisites

- Docker & Docker Compose
- .NET 10 SDK

### Installing .NET 10 on Ubuntu

.NET 10 requires the install script (not yet available in package repositories):

```bash
# Download and run the install script
curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 10.0

# Add to PATH (add to ~/.bashrc for persistence)
export DOTNET_ROOT=$HOME/.dotnet
export PATH=$PATH:$DOTNET_ROOT
```

## Configuration

### stack.json (Defaults)

Base configuration committed to the repository. Do not edit directly.

```json
{
  "project_name": "stack",
  "data_path": "/docker/data",
  "backup_path": "/docker",
  "networks": {
    "proxy": {},
    "database": {}
  },
  "services": [
    "00-resticker"
  ]
}
```

### stack.local.json (Your Configuration)

Create this file to override defaults. This file is gitignored.

Example (Minimal List):

```json
{
  "project_name": "deep-swarm-local",  
  "services": [
    "10-postgres",   
    "20-dozzle",
    "20-n8n",
    "20-pgadmin",
    "90-caddy"
  ]
}
```

Rename `data_path`, `backup_path`, `backup_output_path`.

Edit services.

### Renaming the Stack

> **Warning:** Do not rename `project_name` in `stack.json` after services have been started. The project name is used as a prefix for Docker containers and networks (e.g., `stack-n8n-1`). Changing it will:
> - Leave old containers running under the old name
> - Create duplicate containers under the new name
> - Cause `update.cs` orphan detection to miss the old containers
>
> If you must rename, first stop all services with `./scripts/stop.cs`, then rename.


### .env (Secrets)

Environment variables for services. Copy from `.env.example` and customize.

## Service Overrides

Create files in `overrides/` to customize service configuration:

```bash
cp overrides/90-caddy.override.yml.example overrides/90-caddy.override.yml
```

Standard Docker Compose override format - add ports, environment variables, volumes, etc.

## Available Services

| Service | Description | Internal Port | HTTPS Port |
|---------|-------------|---------------|------------|
| 00-resticker | Restic backup | - | - |
| 10-postgres | PostgreSQL 18 + pgVector | 5432 | - (not exposed) |
| 11-garage | S3-compatible object storage | 3900, 3909 | 8084 (UI), 8085 (S3) |
| 20-n8n | Workflow automation | 5678 | 8080 |
| 15-presidio | PII detection & anonymization | 5002, 5003 | 8090 |
| 20-appsmith | Low-code platform | 80 | 8081 |
| 20-pgadmin | Database admin | 80 | 8082 |
| 20-litellm | AI gateway proxy | 4000 | 8083 |
| 20-nextcloud | File sync & share | 80 | 8086 |
| 20-ragflow | Document AI & RAG | 80 | 8087 |
| 20-dozzle | Docker log viewer | 8080 | 8088 |
| 20-skyvern | AI browser automation | 8000, 8080 | 8089 |
| 90-caddy | Reverse proxy + landing page | - | 443, 8080-8090 |

**Note:** Services don't expose ports directly. Configure Caddy to route HTTPS ports to internal services.

## Network Architecture

### Multi-Port HTTPS

All services are accessed through Caddy reverse proxy. Each service gets its own HTTPS port:

| Port | Service | URL |
|------|---------|-----|
| 443  | Landing Page | `https://localhost` |
| 8080 | n8n | `https://localhost:8080` |
| 8081 | Appsmith | `https://localhost:8081` |
| 8082 | pgAdmin | `https://localhost:8082` |
| 8083 | LiteLLM | `https://localhost:8083` |
| 8084 | Garage UI | `https://localhost:8084` |
| 8085 | Garage S3 | `https://localhost:8085` |
| 8086 | Nextcloud | `https://localhost:8086` |
| 8087 | RAGflow | `https://localhost:8087` |
| 8088 | Dozzle | `https://localhost:8088` |
| 8089 | Skyvern | `https://localhost:8089` |
| 8090 | PII Analyzer | `https://localhost:8090` |

```
Internet/Intranet
        │
        ▼ :443, :8080-8090
┌──────────────────────────────────────┐
│               Caddy                  │
│  :443  → landing page                │
│  :8080 → n8n:5678                    │
│  :8081 → appsmith:80                 │
│  :8082 → pgadmin:80                  │
│  :8083 → litellm:4000                │
│  :8084 → garage-webui:3909           │
│  :8085 → garage:3900 (S3 API)        │
│  :8086 → nextcloud:80                │
│  :8087 → ragflow:80                  │
│  :8088 → dozzle:8080                 │
│  :8089 → skyvern-ui:8080             │
│  :8090 → presidio-analyzer:5002      │
└──────────────────────────────────────┘
        │ proxy network
        ▼
┌───────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ ┌─────────────┐ ┌───────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐
│  n8n  │ │appsmith │ │ pgadmin │ │ litellm │ │ garage │ │garage-webui │ │ nextcloud │ │ ragflow │ │ dozzle │ │ skyvern │ │ presidio │
└───┬───┘ └────┬────┘ └────┬────┘ └────┬────┘ └───┬────┘ └─────────────┘ └─────┬─────┘ └────┬────┘ └────────┘ └────┬────┘ └────┬─────┘
    │          │           │           │          │                             │            │                      │            │
    │          │           │           │          │   ai-internal network       │            │                      │            │
    │          │           │           ├──────────┼────────────────────────────┼────────────┤──────────────────────┤────────────┤
    │          │           │           │          │                             │            │                      │            │
    │          │           │           │          │                             │            │                      │       ┌────┴────┐
    │          │           │           │          │                             │            │                      │       │ gliner  │
    │          │           │           │          │                             │            │                      │       └─────────┘
    │          │           │           │                                        │                                   │
    └──────────┴───────────┴───────────┴───────────────────────────────────────┴───────────────────────────────────┘
                                       │ database network
                               ┌───────┴───────┐
                               │   postgres    │
                               └───────────────┘
```

### Networks

- **proxy**: Web-facing services that need reverse proxy access
- **database**: Services that need PostgreSQL access
- **ai-internal**: Internal AI/ML service communication (n8n, litellm, garage, ragflow, skyvern, presidio)

### TLS Certificates

- For `.local` / internal domains: `tls internal` generates self-signed certs
- For public domains: Caddy auto-fetches Let's Encrypt certificates

## Authentication (caddy-security)

The stack uses [caddy-security](https://github.com/greenpau/caddy-security) for centralized authentication across all services.

### Initial Setup

1. **Generate JWT signing key:**
   ```bash
   # Set CADDY_JWT_SHARED_KEY in .env (already present from .env.example)
   # Generate a value with: openssl rand -hex 32
   ```

2. **Create and configure users:**
   ```bash
   # Initialize user database
   dotnet run scripts/caddy-users.cs init

   # Add your first user
   dotnet run scripts/caddy-users.cs add
   ```

3. **Rebuild Caddy with security plugin:**
   ```bash
   docker compose -f services/90-caddy/docker-compose.yml build --no-cache
   ```

4. **Start/restart the stack:**
   ```bash
   ./scripts/start.cs
   ```

### Authentication Exceptions

| Service | Path | Authentication |
|---------|------|----------------|
| n8n | `/webhook*`, `/webhook-test/*`, `/webhook-waiting/*` | NOT required |
| Garage S3 API (port 8085) | All paths | NOT required (uses S3 auth) |
| All other services | All paths | Required |

### Managing Users

```bash
# List all users
dotnet run scripts/caddy-users.cs list

# Add a new user
dotnet run scripts/caddy-users.cs add

# Generate a password hash manually
dotnet run scripts/caddy-users.cs hash
```

Users are stored in `services/90-caddy/users.json` (gitignored). After modifying users, restart Caddy:

```bash
docker compose -f services/90-caddy/docker-compose.yml restart
```

## Landing Page

A customizable landing page is served at port 443, providing quick access to all services.

### Configuration

Copy `landing.yaml.example` to `landing.yaml`, then customize:

```yaml
title: "My Stack"

groups:
  - name: "Applications"
    links:
      - name: "n8n"
        url: "https://localhost:8080"
        icon: "n8n"
        description: "Workflow Automation"
```

### Regenerate After Changes

After modifying `landing.yaml`, regenerate the static HTML:

```bash
./scripts/generate-landing.cs
```

This creates `services/90-caddy/static/index.html`.

## Scripts

| Command | Description |
|---------|-------------|
| `./scripts/start.cs` | Start all enabled services |
| `./scripts/stop.cs` | Stop all services (reverse order) |
| `./scripts/update.cs` | Git pull + recreate changed containers |
| `./scripts/status.cs` | Show running containers |
| `./scripts/generate-landing.cs` | Regenerate landing page from `landing.yaml` |
| `./scripts/caddy-users.cs` | Manage Caddy authentication users |
| `./scripts/release.cs` | Create a new version release |

## Creating Releases

The stack uses semantic versioning stored in a `VERSION` file at the repository root. The version is displayed on the landing page (in groups with `showVersion: true`).

### Creating a Release

```bash
# Show current version
./scripts/release.cs

# Create a new release (e.g., v1.1.0)
./scripts/release.cs 1.1.0

# Push the release
git push && git push --tags
```

The release script will:
1. Validate the version format (must be `X.Y.Z`)
2. Check for uncommitted changes
3. Update the `VERSION` file
4. Commit with message `chore: release v1.1.0`
5. Create a git tag `v1.1.0`

After creating a release, regenerate the landing page to show the new version:

```bash
./scripts/generate-landing.cs
```

## Automatic Updates (Cron)

To automatically update the stack daily, add this line to your crontab (`crontab -e`):

```bash
# Update stack at 6 AM daily (after backup/prune/check at 3-5 AM)
0 6 * * * cd /docker/config && dotnet run scripts/update.cs >> /var/log/stack-update-$(date +\%Y\%m).log 2>&1
```

> **Note:** Creates one log file per month (e.g., `stack-update-202506.log`). Delete old files manually as needed.

This will:
- Pull the latest changes from the git repository
- Pull updated Docker images
- Recreate containers only if their image changed

## Backup Strategy

The `00-resticker` service uses [restic](https://restic.net/) to backup `/docker` (which contains both config and data).

Configure in `.env`:
- `RESTIC_REPOSITORY`: Backup destination (S3, local, etc.)
- `RESTIC_PASSWORD`: Encryption password
- `BACKUP_CRON`: Schedule (default: `0 3 * * *` = daily at 3 AM)

## Object Storage (Garage)

Garage provides S3-compatible object storage for AI/ML assets, file sharing, and backups.

### Initial Setup

1. **Configure Garage:**
   ```bash
   # Generate secrets and add to .env
   echo "GARAGE_RPC_SECRET=$(openssl rand -hex 32)" >> .env
   echo "GARAGE_ADMIN_TOKEN=$(openssl rand -hex 32)" >> .env
   ```

2. **Configure WebUI authentication:**
   ```bash
   # Generate bcrypt password hash (requires apache2-utils)
   htpasswd -nbBC 10 "admin" "your-password"
   # Add output to .env as GARAGE_WEBUI_AUTH=admin:$2y$10$...
   ```

3. **Start the stack** and initialize the cluster:
   ```bash
   ./scripts/start.cs

   # Get node ID
   docker exec garage /garage node id

   # Configure node layout (replace <node-id> with actual ID)
   docker exec garage /garage layout assign -z dc1 -c 10G <node-id>

   # Apply layout
   docker exec garage /garage layout apply --version 1
   ```

### Create Buckets and Access Keys

```bash
# Create a bucket
docker exec garage /garage bucket create my-bucket

# Create an access key
docker exec garage /garage key create my-key

# Grant read/write access
docker exec garage /garage bucket allow --read --write my-bucket --key my-key

# View key credentials (access_key_id and secret_access_key)
docker exec garage /garage key info my-key --show-secret
```

### S3 Client Configuration

```bash
# AWS CLI
aws configure set aws_access_key_id <access_key_id>
aws configure set aws_secret_access_key <secret_access_key>
aws configure set default.region garage

# Example: List buckets
aws --endpoint-url https://localhost:8085 --no-verify-ssl s3 ls

# Example: Upload file
aws --endpoint-url https://localhost:8085 --no-verify-ssl s3 cp file.bin s3://my-bucket/
```

### Bucket Lifecycle (Expiration Policy)

Create a lifecycle configuration file to auto-delete old objects:

```bash
# Create lifecycle.json
cat > /tmp/lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "ID": "expire-after-30-days",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "Expiration": { "Days": 30 }
    }
  ]
}
EOF

# Apply lifecycle policy using AWS CLI (or any S3 client)
aws --endpoint-url https://localhost:8085 --no-verify-ssl s3api put-bucket-lifecycle-configuration \
  --bucket my-bucket \
  --lifecycle-configuration file:///tmp/lifecycle.json

# Verify lifecycle policy was applied
aws --endpoint-url https://localhost:8085 --no-verify-ssl s3api get-bucket-lifecycle-configuration \
  --bucket my-bucket
```

**Lifecycle rule examples:**
- Expire all objects after 30 days: `"Expiration": { "Days": 30 }`
- Expire objects with prefix: `"Filter": { "Prefix": "temp/" }`
- Expire on specific date: `"Expiration": { "Date": "2025-12-31T00:00:00Z" }`

### Public File Sharing

Generate presigned URLs for temporary, time-limited access to private objects without making the bucket public. The generated URL includes authentication in the query string, so recipients can access the file without any credentials.

```bash
# Generate a presigned URL for temporary file access (default: 1 hour)
aws --endpoint-url https://localhost:8085 --no-verify-ssl s3 presign s3://my-bucket/filename

# Specify custom expiration time (e.g., 7 days = 604800 seconds)
aws --endpoint-url https://localhost:8085 --no-verify-ssl s3 presign s3://my-bucket/filename --expires-in 604800
```

### Access URLs

| Port | Purpose | URL |
|------|---------|-----|
| 8084 | Web UI (management) | `https://localhost:8084` |
| 8085 | S3 API (uploads/downloads) | `https://localhost:8085` |

## LiteLLM (AI Gateway)

LiteLLM provides a unified API gateway for multiple AI providers (OpenAI, Anthropic, Azure, etc.).

Documentation: https://docs.litellm.ai/

## n8n (Workflow Automation)

### First-Time Setup

Before starting n8n for the first time, create the data directory with correct permissions:

```bash
sudo mkdir -p /docker/data/n8n
sudo chown -R 1000:1000 /docker/data/n8n
```

This is required because n8n runs as UID 1000 (node user) inside the container.

## RAGFlow (Document AI & RAG)

RAGFlow is a document AI platform for RAG (Retrieval-Augmented Generation).

### First-Time Setup

Before starting RAGFlow for the first time, create the Elasticsearch data directory with correct permissions:

```bash
sudo mkdir -p /docker/data/ragflow/elasticsearch
sudo chown -R 1000:1000 /docker/data/ragflow/elasticsearch
```

This is required because Elasticsearch runs as UID 1000 inside the container.

### Access

- **URL:** `https://localhost:8087`
- **Default credentials:** Set during first login

### Troubleshooting

**Elasticsearch fails to start with permission error:**
```
java.nio.file.AccessDeniedException: /usr/share/elasticsearch/data/node.lock
```

Fix by ensuring correct ownership:
```bash
sudo chown -R 1000:1000 /docker/data/ragflow/elasticsearch
```

## Skyvern (AI Browser Automation)

Skyvern uses LLM-powered agents to automate web browser interactions.

### First-Time Setup

After starting Skyvern for the first time, you need to get the API key:

1. **Access the Skyvern UI:** `https://localhost:8089`
2. **Navigate to Settings** (gear icon)
3. **Regenerate the API key** using the button in the UI
4. **Copy the key** and add it to your `.env` file:
   ```bash
   SKYVERN_API_KEY=eyJhbGciOiJIUzI1NiIs...
   ```
5. **Restart the stack** to apply the new key:
   ```bash
   ./scripts/stop.cs && ./scripts/start.cs
   ```

> **Note:** The API key is a JWT token generated by Skyvern, not a random string. Do not use `openssl rand` to generate it.

### LLM Configuration

Skyvern routes LLM requests through LiteLLM. Configure the model in `.env`:

```bash
SKYVERN_LLM_MODEL=openai/gpt-5.2
SKYVERN_LLM_API_KEY=your-litellm-master-key
```

## Presidio PII Analyzer

PII detection and anonymization using an ensemble of NerGuard + GLiNER models via Microsoft Presidio, with optional LiteLLM guardrail integration.

### First-Time Setup

The first start takes significantly longer than usual:

- **GLiNER sidecar** — compiles a Rust binary and exports the ONNX model during the Docker build. Expect 5–15 minutes depending on CPU.
- **Presidio Analyzer** — downloads the NerGuard-0.3B model (~600 MB) on first startup. The model is cached in `${DATA_PATH}/presidio/model-cache` for subsequent starts.
- **Frontend** — a one-shot container that builds the React app and copies the static files to `${DATA_PATH}/presidio/frontend-dist`. Caddy serves them from there.

The analyzer health check has a `start_period` of 120s to accommodate model loading. Monitor progress with:

```bash
docker compose -f services/15-presidio/docker-compose.yml logs -f
```

### Access

- **URL:** `https://localhost:8090`
- **API:** Routes like `/analyze`, `/anonymize`, `/health` are proxied to the analyzer

## Nextcloud (File Sync & Share)

### Reverse Proxy Configuration

When running behind Caddy (or any reverse proxy handling HTTPS), Nextcloud needs to know the external URL. Without this, login redirects may fail silently.

After first-time setup, edit Nextcloud's config file:

```bash
nano ${DATA_PATH}/nextcloud/config/config.php
```

Add these settings inside the `$CONFIG` array:

```php
'overwrite.cli.url' => 'https://your-domain:8086',
'overwritehost' => 'your-domain:8086',
'overwriteprotocol' => 'https',
```

Replace `your-domain` with your actual domain (e.g., `localhost` or `myserver.example.com`).

**Symptoms of missing configuration:**
- After login, page doesn't redirect (nothing happens)
- Reloading the page shows you're logged in
- Browser console may show mixed content warnings

## Adding New Services

1. Create `services/{NN}-{name}/docker-compose.yml`
   - Use `00-` for infrastructure (backup, monitoring)
   - Use `10-` for databases and core services
   - Use `20-` for applications

2. Use appropriate networks:
   - `proxy` for web-facing services
   - `database` for PostgreSQL access

3. Do NOT expose ports directly - access via Caddy

4. Mount data to `${DATA_PATH}/{name}`

5. Add to `stack.local.json` services array

6. Add database init if needed in `services/10-postgres/init/`

7. Add entry to `services/90-caddy/Caddyfile`

8. Add the port to `overrides/90-caddy.override.yml`

### Example Service

```yaml
# services/20-myapp/docker-compose.yml
services:
  myapp:
    image: myapp:latest
    hostname: myapp
    volumes:
      - ${DATA_PATH}/myapp:/data
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/myapp
    networks:
      - proxy
      - database
    restart: unless-stopped

networks:
  proxy:
    name: ${PROJECT_NAME}_proxy
    external: true
  database:
    name: ${PROJECT_NAME}_database
    external: true
```

## Directory Structure

```
docker-stack/
├── scripts/              # .NET 10 management scripts
│   ├── start.cs
│   ├── stop.cs
│   ├── update.cs
│   ├── status.cs
│   ├── generate-landing.cs
│   ├── caddy-users.cs
│   └── release.cs
├── VERSION               # Semantic version (e.g., 1.0.0)
├── services/             # Service definitions
│   ├── 00-resticker/
│   ├── 10-postgres/
│   ├── 11-garage/
│   ├── 15-presidio/
│   ├── 20-appsmith/
│   ├── 20-litellm/
│   ├── 20-n8n/
│   ├── 20-nextcloud/
│   ├── 20-pgadmin/
│   ├── 20-ragflow/
│   ├── 20-skyvern/
│   └── 90-caddy/
│       └── static/       # Generated landing page (gitignored)
├── overrides/            # Service overrides (gitignored)
├── stack.json            # Default configuration
├── stack.local.json      # Your configuration (gitignored)
├── landing.yaml.example  # Landing page template
├── landing.yaml          # Your landing config (gitignored)
├── .env.example          # Environment template
└── .env                  # Your secrets (gitignored)
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

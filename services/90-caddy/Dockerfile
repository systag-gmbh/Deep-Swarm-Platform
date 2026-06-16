# Build stage: compile Caddy with caddy-security plugin
FROM caddy:2-builder AS builder

RUN xcaddy build \
    --with github.com/greenpau/caddy-security

# Runtime stage: use official Alpine image
FROM caddy:2-alpine

# Copy the custom-built Caddy binary
COPY --from=builder /usr/bin/caddy /usr/bin/caddy

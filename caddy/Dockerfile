FROM caddy:2-builder AS builder

# All DNS providers are compiled in so one image serves every TLS_MODE. Caddy
# has no runtime plugin loading, so a provider not built here cannot be named in
# a Caddyfile. Adding another is one more --with line and a rebuild; the full
# list is at https://github.com/caddy-dns
RUN xcaddy build \
    --with github.com/caddy-dns/route53 \
    --with github.com/caddy-dns/godaddy \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy

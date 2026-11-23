# Deploying in your own environment

This lab was built against Route53, but nothing about it requires AWS. This
guide covers standing it up with whatever DNS you already have.

## The only hard requirement

**WaaS must be able to reach your origin over the public internet.** Everything
else is negotiable. If the origin is only reachable on your LAN or via a
`/etc/hosts` entry, you can develop against the app but you cannot demonstrate
the WAF, which is the entire point.

So you need:

| Record | Type | Points at | Who creates it |
|---|---|---|---|
| `$INSECURE_HOST` | A | your host's public IP | you, at your DNS provider |
| `$SECURE_HOST` | CNAME | the WaaS endpoint (`app######.prod.cudawaas.com`) | you, from the value WaaS shows you |

Any DNS provider can do both. They are ordinary records created in a web
console.

## Pick a TLS mode

The one thing that *can* need DNS API access is the certificate for
`$INSECURE_HOST`. Set `TLS_MODE` in `.env`.

**`$SECURE_HOST` never needs a certificate from you** — WaaS terminates TLS at
its edge and talks plain HTTP to your origin on `:8081`. So this decision only
ever concerns the insecure hostname.

```
Is port 80 reachable from the internet on your host?
├─ Yes  -> TLS_MODE=http01          <- the right answer for most people
└─ No   -> does your DNS provider have a Caddy module?
           ├─ Route53     -> TLS_MODE=dns01-route53
           ├─ GoDaddy     -> TLS_MODE=dns01-godaddy
           ├─ Cloudflare  -> TLS_MODE=dns01-cloudflare
           └─ anything else (incl. Barracuda DNS Zones)
                          -> open port 80 and use http01, or see
                             "Other DNS providers" below
```

### `http01` (default)

Caddy answers the ACME challenge over port 80. **No DNS API credentials at
all.** Works with GoDaddy, Barracuda WaaS DNS Zones, Namecheap, a registrar's
web console — anything, because Caddy never talks to your DNS provider.

Requirements:

- An A record for `$INSECURE_HOST` resolving to your host **before** `make up`.
  Caddy will fail issuance and retry if the name does not resolve yet.
- Inbound **port 80** open from the internet. Let's Encrypt validates from its
  own infrastructure, so an ACL restricted to your office IP will not work.
- Inbound **port 443** open, for the demo itself.

```bash
TLS_MODE=http01
INSECURE_HOST=insecure.pay.yourdomain.com
SECURE_HOST=secure.pay.yourdomain.com
ACME_EMAIL=you@yourdomain.com
LAB_DOMAINS=.yourdomain.com
```

### `dns01-godaddy`

Only worth it when port 80 cannot be opened. Create an API key at
<https://developer.godaddy.com/keys> and combine it as `KEY:SECRET`:

```bash
TLS_MODE=dns01-godaddy
GODADDY_API_TOKEN=dL9...:Uk3...
```

GoDaddy gates production API access on account tier, and keys from the OTE
(test) environment will not work against production DNS. If the key will not
authenticate, open port 80 and use `http01` rather than fighting it.

### `dns01-route53` / `dns01-cloudflare`

```bash
TLS_MODE=dns01-route53
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

```bash
TLS_MODE=dns01-cloudflare
# Scoped token with Zone:DNS:Edit. The legacy Global API Key will NOT work.
CLOUDFLARE_API_TOKEN=...
```

Either needs permission to write TXT records in the zone containing
`$INSECURE_HOST`.

### `internal`

Caddy issues from its own local CA. No public DNS, no ACME, no internet.

```bash
TLS_MODE=internal
INSECURE_HOST=insecure.pay.cudalab.test
SECURE_HOST=secure.pay.cudalab.test
LAB_DOMAINS=.cudalab.test
```

```
# /etc/hosts
127.0.0.1  insecure.pay.cudalab.test  secure.pay.cudalab.test
```

Attack scripts need `--insecure` to accept the local CA:

```bash
python3 t1_blast.py --target https://insecure.pay.cudalab.test --count 200 --insecure
```

**WaaS cannot reach an origin that only resolves on your laptop**, so the secure
half of the demo does not work in this mode. Use it to build, modify or rehearse
against the unprotected side, then switch to `http01` for anything a customer
will see.

## Using Barracuda WaaS DNS Zones

If you host the zone in WaaS itself, this gets simpler, not harder — you manage
both records in the same console as the application.

1. **DNS Zones > Add DNS Zone**, enter your domain.
2. Optionally import existing records.
3. At your registrar, **change the NS records** to the nameservers WaaS gives
   you. Propagation takes up to a few hours; nothing below works until it lands.
4. In the WaaS DNS zone, add an **A record** for `insecure.pay.<domain>`
   pointing at your host's public IP.
5. Create the WaaS **application** for `secure.pay.<domain>` with origin
   `<your-host-ip>:8081`. With the zone hosted in WaaS you can use an
   application pointer instead of hand-entering the CNAME.
6. Set `TLS_MODE=http01`. **There is no Caddy DNS module for Barracuda DNS
   Zones**, so DNS-01 is not available — but you do not need it.

Two caveats worth knowing in advance:

- **Record count is capped by your licence plan.** This lab needs two. Check
  your plan if the zone is already busy.
- Barracuda's documentation warns not to reuse a domain across multiple WaaS
  applications when its DNS is WaaS-managed, and not to import snapshots
  containing the same domain. Give the lab its own subdomain.

## Other DNS providers

Caddy has modules for most providers at <https://github.com/caddy-dns>. Caddy
has **no runtime plugin loading**, so a provider must be compiled in. Add a line
to `caddy/Dockerfile`:

```dockerfile
RUN xcaddy build \
    --with github.com/caddy-dns/route53 \
    --with github.com/caddy-dns/godaddy \
    --with github.com/caddy-dns/cloudflare \
    --with github.com/caddy-dns/YOURPROVIDER
```

Then copy `caddy/Caddyfile.dns01-godaddy` to
`caddy/Caddyfile.dns01-yourprovider`, change the `dns` line to match that
module's syntax, set `TLS_MODE=dns01-yourprovider`, and `make build && make up`.

Verify the module compiled in:

```bash
docker run --rm waf-demo-credit-cards_caddy:latest caddy list-modules | grep dns.providers
```

## Hosting the origin somewhere other than Azure

Nothing is Azure-specific; the stack is Docker Compose and needs a public IP
with ports 80, 443 and 8081 reachable. The only platform-specific step is the
firewall rule restricting `:8081` to Barracuda WaaS source ranges — an NSG on
Azure, a security group on AWS, `ufw` on a bare VM. Do not skip it: if a
prospect can reach the origin directly, the "protected" side of the demo is
arguable.

Port 8081 rather than 8080 is a local accident of the original host, where
another stack held 8080. If 8080 is free for you, change it in
`docker-compose.yml` and `caddy/origin.caddyfile` together.

## Checking it worked

```bash
make up
docker-compose logs caddy | grep -i "certificate obtained"   # TLS issuance
curl -s https://$INSECURE_HOST/healthz                        # public side
curl -s -H "Host: $SECURE_HOST" localhost:8081/healthz        # WaaS origin
curl -s localhost:8081/                                       # expect: Not found
```

If issuance fails, the log line names the reason. The usual causes are the A
record not resolving yet, port 80 blocked while using `http01`, or DNS API
credentials lacking write access to the zone.

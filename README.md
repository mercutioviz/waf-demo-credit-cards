# waf-demo-credit-cards

A carding attack lab for Barracuda WAF-as-a-Service demos. A deliberately
unprotected Tek Gear checkout form, four attacker tiers that escalate against
it, and a live dashboard showing the victim's side of the attack.

Built for the case where a customer's payment form is being abused by bots
testing stolen cards (OWASP OAT-001 Carding and OAT-010 Card Cracking).

## Why it is built as a ladder

A single on/off WAF toggle makes a weak carding demo, because the honest answer
is that **rate limiting alone does not stop carding**. Each tier here defeats the
control that stopped the one below it:

| Tier | Attacker | Stopped by |
|---|---|---|
| 1 | Blind POST flood, one IP | Brute Force Prevention |
| 2/3 | Session-aware, throttled, UA rotation | Bot Protection (TLS fingerprint, UA analysis) |
| 4 | Headless Chromium | Advanced Bot Protection (browser integrity, device velocity) |
| 5 | Card cracking against one PAN | Brute force + a developer fix the WAF does not own |

The prospect watches each control get defeated until bot fingerprinting ends it.
That structure is what makes the Advanced Bot Protection case, and it survives
the objection a one-toggle demo invites.

## Quick start

```bash
cp .env.example .env     # set LAB_SECRET and AWS Route53 credentials
make build
make up
```

Then:

```bash
cd attack
pip install -r requirements.txt
export LAB_SECRET=<same value as .env>
python3 t1_blast.py --target https://insecure.pay.democuda.org --count 500
```

Watch `https://insecure.pay.democuda.org/ops` while it runs.

The SA playbook is `docs/demo-script.md`. Read that before running a live demo.

## Topology

```
Internet
  ├─ insecure.pay.democuda.org ─ A ─→ host:443 ─ Caddy ─→ checkout-insecure  (no WAF)
  └─ secure.pay.democuda.org ─ CNAME ─→ Barracuda WaaS ─→ host:8081 ─ Caddy ─→ checkout-secure
```

Both instances run the same image and share `LAB_SECRET`, so a card that is live
on one is live on the other and the before/after comparison is like-for-like.
They differ only by `INSTANCE_NAME`, which `/ops` displays so two browser panes
are tellable apart.

All state is in-memory. There is no database and no volumes — `make reset` or
the dashboard button zeroes a run instantly, which is what you actually need
between demo attempts.

### Ports

| Port | Use |
|---|---|
| 80 | Caddy, redirects to HTTPS |
| 443 | Caddy, `insecure.pay.democuda.org` |
| 8081 | Caddy, WaaS origin for `secure.pay.democuda.org` |

Port 8081 rather than the usual 8080 because `waf-training-wordpress` already
holds 8080 and 8443 on this host. Caddy binds 80 and 443, so this stack and
`waf-firing-range` cannot run at the same time.

## Manual setup

These cannot be scripted from inside the repo.

1. **Route53** — A record `insecure.pay.democuda.org` → the host's public IP.
   Put AWS credentials in `.env` so Caddy can complete the DNS-01 challenge.
2. **Azure NSG** — allow `:443` from any; allow `:8081` **only from Barracuda
   WaaS source ranges**. If a prospect can reach the origin directly, the demo
   is arguable.
3. **WaaS console** — create the application with origin `<host-ip>:8081` and
   **preserve the Host header** (Caddy routes on it). Point
   `secure.pay.democuda.org` at the WaaS endpoint.
4. **Confirm the ABP entitlement** if you intend to demonstrate tier 4.

See `configs/waf/README.md` for the per-rung policy notes.

## Safety

- Every card is synthetic, generated against published sandbox BIN ranges.
- The issuer is a local fake. Liveness, expiry and CVV derive from
  `HMAC-SHA256(LAB_SECRET, PAN)` — repeatable here, meaningless anywhere else.
- No payment network is involved and no real card data exists in this lab.
- `/ops` only ever displays a masked PAN (first six, last four).
- The attack scripts refuse any host outside `*.democuda.org` and localhost
  unless `--force` is given, which prints a warning.

`LAB_SECRET` is never committed. `.env` is gitignored.

## Layout

```
app/        Flask checkout, fake issuer, telemetry, /ops dashboard
attack/     The four attacker tiers plus shared card/dump helpers
brand/      Tek Gear assets, vendored from waf-firing-range
caddy/      Custom Caddy build (Route53 DNS-01) and vhosts
configs/    WaaS policy notes, one section per demo rung
docs/       SA demo script
```

## Related

- `waf-firing-range` — deliberately vulnerable apps for kast regression testing.
  This repo borrows its conventions and Tek Gear brand, but is standalone.

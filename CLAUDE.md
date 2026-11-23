# waf-demo-credit-cards — Active Context for AI Assistants

This file is auto-loaded by Claude Code on every session in this repo.

## Project purpose

A carding attack lab for Barracuda WAF-as-a-Service demos, built for a specific
customer case: a checkout form carrying credit card fields is being abused by
bots testing stolen cards.

The audience is Barracuda SAs and partner sales engineers running a live
before/after demo in front of a prospect. The app is intentionally vulnerable
and must never be exposed on a public IP without either a WAF in front of it or
an NSG restricting access.

## The core design decision

This is built as an **escalation ladder**, not an on/off toggle, because the
honest answer about carding is unflattering to a naive pitch: rate limiting
alone does not stop it. Each attacker tier defeats the control that stopped the
tier below.

Every change should preserve that structure. A change that makes the WAF look
like it fixes everything makes the demo *less* persuasive, not more — it invites
the one objection an SA cannot answer.

## Topology

| Instance | Route | Who reaches it |
|---|---|---|
| `checkout-insecure` | `$INSECURE_HOST` → host:443 → Caddy | Public internet |
| `checkout-secure` | `$SECURE_HOST` → WaaS → host:8081 → Caddy | WaaS only (NSG-restricted) |

**Hostnames are not hardcoded.** `INSECURE_HOST`, `SECURE_HOST`, `ACME_EMAIL`
and `LAB_DOMAINS` live in `.env` and flow to Caddy (via compose env, substituted
as `{$VAR}` in the Caddyfile), to the Makefile (sourced in a shell, not
`include`d, so odd values cannot break the parse), and to the attack scripts.
Defaults are the `democuda.org` names. If you add a hostname reference, read it
from one of those rather than writing a literal.

**TLS is pluggable.** `TLS_MODE` selects which `caddy/Caddyfile.<mode>` compose
mounts: `http01` (default), `dns01-route53`, `dns01-godaddy`,
`dns01-cloudflare`, `internal`. Each is a small file importing the shared
`caddy/origin.caddyfile`, which holds the `:8081` WaaS origin block — that block
is mode-independent because **WaaS terminates TLS at its edge, so the secure
side never needs a certificate**. Keep it that way: TLS changes belong in the
mode files only.

All DNS provider modules are compiled into one image. Caddy has no runtime
plugin loading, so adding a provider means a `--with` line in `caddy/Dockerfile`
plus a new mode file. Prefer `http01` in docs and defaults — most deployments do
not need DNS API credentials, and recommending otherwise sends SAs chasing
provider keys they do not need.

`--insecure` on the attack scripts exists for `internal` mode, where Caddy
issues from its own local CA. It sets `verify=False` on the requests Session and
`ignore_https_errors` on the Playwright context.

Both run the same image and share `LAB_SECRET` so the comparison is
like-for-like. They differ only by `INSTANCE_NAME`.

**Port 8081, not 8080.** The `waf-training-wordpress` stack holds 8080 and 8443
on this host. Caddy binds 80 and 443, so this stack and `waf-firing-range`
cannot run simultaneously.

## State

Everything is in-memory, per container. No database, no volumes, no seed
snapshots. `POST /ops/reset` zeroes a run instantly, which is what an SA needs
between demo attempts.

**Gunicorn runs one worker on purpose** (`--workers 1 --threads 32`). Telemetry
lives in process memory; a second worker would split the counters and silently
desync the dashboard mid-demo. Do not "fix" this by adding workers — if the app
ever needs to scale, the telemetry has to move out of process first.

## The fake issuer

`app/tekgear/issuer.py`. Liveness, expiry and CVV all derive from
`HMAC-SHA256(LAB_SECRET, PAN)`. Deterministic, so demos are repeatable across
restarts; meaningless outside this lab.

`attack/labcards.py:derive_credentials()` **mirrors this derivation.** If you
change the derivation in one, change it in the other or every attack run returns
code 05.

The decline codes are deliberately distinguishable — 54 for a wrong expiry, 82
for a wrong CVV. That is not an oversight. It is the vulnerability tier 5
exploits, and the developer-fix point the demo closes on.

## Safety invariants

**This repository is public.** Do not weaken any of these.

- Synthetic cards only, from published sandbox BIN ranges. No real PANs, ever.
- No real payment gateway. The issuer stays local and fake.
- `/ops` displays masked PANs only (first six, last four).
- `labcards.guard_target()` allowlists `LAB_DOMAINS` plus loopback. `--force`
  overrides it but **requires `--authorization`** — do not make the override
  usable on its own, and do not let loopback drop out of the always-allowed set.
- `labcards.preflight()` prints the authorised-use banner. Every attack script
  calls it first. A new tier must call it too.
- `LAB_SECRET` is env-sourced and never committed, so the live-card oracle is
  not baked into the repo.

## Licence and disclaimers

Apache-2.0, chosen over MIT for the express patent grant, the trademark clause
(§6, so a fork cannot imply Barracuda endorsement), the explicit limitation of
liability (§§7–8), and the `NOTICE` mechanism — §4(d) requires redistributors to
carry it, which is how the authorised-use terms survive a fork.

Copyright is **Barracuda Networks, Inc.** — this was built on company resources,
unlike the sibling `waf-firing-range`, which is personally owned and MIT. Do not
copy that repo's licence or copyright line over.

`NOTICE` is load-bearing, not boilerplate. It carries the authorised-use terms,
the no-real-cardholder-data warning, and the statement that this is **not a
supported Barracuda product**. Keep that last one precise: Barracuda owns and
publishes this, so it cannot disclaim authorship — what it disclaims is
*support*. It is not part of any product, carries no SLA, and should not
generate Support cases.

No OSI-approved licence can restrict use, so misuse is addressed by three other
layers instead: the `NOTICE`, the runtime banners, and the target allowlist.

## Repository layout

```
waf-demo-credit-cards/
├── docker-compose.yml          # name: waf-demo-credit-cards
├── Makefile                    # up, down, build, logs, ps, reset
├── caddy/                      # custom Caddy build; one Caddyfile per TLS_MODE
│   ├── Dockerfile              # xcaddy with route53, godaddy, cloudflare
│   ├── origin.caddyfile        # shared :8081 WaaS origin block
│   └── Caddyfile.<mode>        # http01 | dns01-* | internal
├── brand/                      # Tek Gear assets, vendored from waf-firing-range
├── app/
│   ├── Dockerfile              # repo-root build context so COPY brand/ works
│   └── tekgear/
│       ├── issuer.py           # fake payment processor
│       ├── telemetry.py        # thread-safe in-memory counters + SSE fanout
│       ├── views_shop.py       # storefront and the checkout target
│       ├── views_ops.py        # dashboard, snapshot, stream, reset
│       ├── templates/
│       └── static/             # app.css, ops.js, brand/ (copied at build)
├── attack/
│   ├── labcards.py             # Luhn gen, dump builder, target guard, tally
│   ├── t1_blast.py             # naive flood
│   ├── t2_slowroll.py          # session-aware, rate-evading
│   ├── t4_browser.py           # Playwright headless
│   └── t5_crack.py             # OAT-010 card cracking
├── configs/waf/                # WaaS policy notes, one section per rung
└── docs/demo-script.md         # the SA playbook
```

## Relationship to waf-firing-range

This repo borrows that one's conventions — Caddyfile shape, compose style, the
`insecure.*`/`secure.*` pair, the Tek Gear brand — but is **standalone** so other
SAs can clone it alone.

Two deliberate divergences:

- **`brand/` is vendored, not shared.** That repo's "do not duplicate brand
  assets" rule binds within it; a standalone repo cannot bind-mount a sibling.
- **No `## Intended kast findings` table.** This is a narrative demo, not a kast
  regression target. App READMEs use `## Deliberate weaknesses` mapped to WaaS
  controls instead, and assets are referenced over HTTPS — the mixed-content
  findings that repo wants deliberately would be noise here.

Note that `waf-firing-range` is currently a scaffold: its infra is real but
every `apps/*/` holds only a README. There is no Flask app there to copy from.

## Dashboard design

`/ops` uses the **emphasis form**: one accent hue (brand orange `#E8660A`) marks
"the attacker got a hit", everything else is de-emphasis ink. A status red was
tried and rejected — it measured only ΔE 11.0 from brand orange for normal
vision against a floor of 15, so the two states would have been hard to tell
apart. Every outcome also carries a text label, so colour is never the only
channel. Keep both properties if you restyle it.

The hero figure is **live cards found** — the number that costs the customer
money. Exactly one hero per view.

## House style

- No emojis in code or docs
- Default to no comments; add one only when the WHY is non-obvious
- Keep it minimal. A demo that breaks in front of a prospect is worse than a
  demo that does less
- All deliberate weaknesses must be documented in `app/README.md`. An
  undocumented vulnerability is a liability
- Vanilla JS on the dashboard. There is no Node toolchain on the demo host, and
  a demo screen that needs a build step is one that breaks at the wrong moment

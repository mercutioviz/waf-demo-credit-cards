# waf-demo-credit-cards

A carding attack lab for Barracuda WAF-as-a-Service demos. A deliberately
unprotected Tek Gear checkout form, four attacker tiers that escalate against
it, and a live dashboard showing the victim's side of the attack.

Built for the case where a customer's payment form is being abused by bots
testing stolen cards (OWASP OAT-001 Carding and OAT-010 Card Cracking).

---

> ## ⚠ Authorised use only
>
> **This repository contains working attack tooling and a deliberately
> vulnerable web application.**
>
> - Run the scripts in `attack/` **only** against systems you own or have
>   **explicit written permission** to test. Unauthorised access to a computer
>   system is a criminal offence in most jurisdictions, including under the US
>   Computer Fraud and Abuse Act and the UK Computer Misuse Act 1990. Testing a
>   third party's payment form without authorisation may additionally
>   constitute payment fraud.
> - **Never supply real cardholder data.** Every card here is synthetic and the
>   issuer is a local fake. The bundled app stores data in memory in the clear,
>   is not PCI-DSS compliant, and must never process genuine payments.
> - **Do not expose `app/` on a public network** without a WAF in front of it or
>   an ACL restricting access. It has no rate limiting, no bot detection and no
>   CSRF protection, by design.
> - This is demonstration material, **not a supported Barracuda product**. It is
>   not part of any Barracuda product and is not covered by any support
>   agreement or SLA. Please don't raise Support cases about it.
> - Provided **without warranty of any kind**. You are responsible for how you
>   use it.
>
> Full terms in [`NOTICE`](NOTICE) and [`LICENSE`](LICENSE).

---

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

## Deploying in your own environment

Nothing here requires AWS or a particular DNS provider. The hostnames and the
certificate strategy both come from `.env`:

```bash
TLS_MODE=http01
INSECURE_HOST=insecure.pay.yourdomain.com
SECURE_HOST=secure.pay.yourdomain.com
ACME_EMAIL=you@yourdomain.com
LAB_DOMAINS=.yourdomain.com
```

```bash
make down && make up
```

`TLS_MODE` picks how Caddy gets a certificate for the insecure hostname — the
secure side never needs one, since WaaS terminates TLS at its edge:

| Mode | Needs | Use when |
|---|---|---|
| `http01` | port 80 open, an A record | **most deployments** — no DNS API credentials, works with any provider including GoDaddy and Barracuda DNS Zones |
| `dns01-route53` | AWS API keys | port 80 cannot be opened |
| `dns01-godaddy` | GoDaddy API token | port 80 cannot be opened |
| `dns01-cloudflare` | Cloudflare scoped token | port 80 cannot be opened |
| `internal` | nothing | offline app work; **WaaS cannot reach the origin, so the secure half of the demo will not work** |

**[`docs/deployment.md`](docs/deployment.md) is the full guide** — per-provider
setup, a walkthrough for Barracuda WaaS DNS Zones, how to add a DNS provider
that isn't bundled, and how to verify issuance worked.

`localhost` and `127.0.0.1` stay permitted regardless of `LAB_DOMAINS`, so you
can always test a container directly. Example commands throughout these docs use
the `democuda.org` defaults.

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
- Every attack script prints an authorised-use banner before it does anything.
- The scripts refuse any host outside `*.democuda.org` and localhost. `--force`
  overrides the allowlist but **cannot be used alone** — it requires
  `--authorization '<engagement, ticket or permission reference>'`, which is
  echoed into the run's output. Stating who authorised the test is cheap; it
  makes an unconsidered run take a deliberate step.

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

## Licence

[Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE) for the attribution and
security-tooling notice, which Apache-2.0 §4(d) requires redistributors to
carry — so the authorised-use terms travel with any fork.

Apache-2.0 rather than MIT for three reasons that matter to a public repository
of offensive tooling: an express patent grant, a trademark clause (§6) so a fork
cannot imply Barracuda endorsement, and a more explicit limitation of liability
(§§7–8) than MIT's single sentence.

Note that no OSI-approved licence can restrict *how* software is used — a
licence that did would not be open source. The licence here limits liability;
the `NOTICE`, the runtime banners, and the target allowlist are what address
misuse. They are separate layers doing separate jobs.

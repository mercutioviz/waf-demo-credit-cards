# app — Tek Gear checkout (Flask / Python)

The Tek Gear storefront reduced to the one journey that matters for this demo:
browse a product, open a checkout form, submit card details. The form is the
carding target. Everything else exists so the funnel looks real to both a
prospect and a bot-detection engine.

## Stack

- Python 3.12
- Flask 3.1
- Gunicorn (1 worker, 32 threads)

## Deliberate weaknesses

Each one maps to a WaaS control in `../configs/waf/`. They are the reason the
unprotected instance loses.

- **No rate limiting on any route**, `POST /checkout` included. A single client
  can submit several hundred cards per second.
- **The response is a free oracle.** "Payment approved" and "Card declined" are
  trivially distinguishable in the body, so a script learns a card's liveness at
  no cost.
- **Decline codes distinguish a wrong expiry (54) from a wrong CVV (82).** This
  splits card cracking from 48,000 requests into at most 1,048. The single most
  damaging weakness here, and the one no rate limit fixes.
- **No CAPTCHA, bot detection, or proof-of-work.** Nothing distinguishes a
  browser from `requests`.
- **No CSRF token on the checkout form.** A bare `POST` with no prior `GET`
  succeeds, so WaaS Form Protection is what adds that requirement back.
- **No velocity check on cards per session or cards per source.** One cookie jar
  may test unlimited distinct PANs.
- **Both outcomes return HTTP 200.** Real payment pages do this, and it denies
  defenders the shortcut of rate-limiting on 4xx.

## What is deliberately *not* weak

The issuer is a local fake. Liveness, expiry and CVV are derived from
`HMAC-SHA256(LAB_SECRET, PAN)`, so results are repeatable across restarts and
meaningless anywhere else. No card data leaves the container, nothing reaches a
payment network, and `/ops` only ever displays a masked PAN (first six, last
four).

## Routes

- `GET /` — product listing, seeded from `brand/products.json`
- `GET /product/<sku>` — product detail
- `GET /checkout` — the card form; issues the session cookie
- `POST /checkout` — authorises against the fake issuer and records telemetry
- `GET /ops` — live attack dashboard
- `GET /ops/snapshot` — current counters and recent attempts as JSON
- `GET /ops/stream` — server-sent event feed backing the dashboard
- `POST /ops/reset` — zero the counters between demo runs
- `GET /healthz` — liveness probe

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `INSTANCE_NAME` | `local` | Shown on `/ops` so two browser panes are tellable apart |
| `LAB_SECRET` | `dev-only-insecure-default` | Seeds the issuer. Both instances must share it for a like-for-like comparison |
| `LIVE_RATE` | `2` | Percentage of cards the issuer treats as live |

## Notes

Gunicorn runs **one worker on purpose**. Telemetry lives in process memory, so a
second worker would split the counters and silently desync the dashboard
mid-demo. Thirty-two threads carry far more load than any tier generates.

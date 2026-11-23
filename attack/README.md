# attack — carding simulations

Four attacker tiers against the Tek Gear checkout. Each one defeats the control
that stopped the tier below it, which is what turns a single on/off WAF toggle
into a demo with a narrative.

## Scope and safety

These scripts only work against this lab.

- Every card is synthetic, generated against published sandbox BIN ranges.
- "Approved" is produced by a local fake issuer keyed on `LAB_SECRET`. There is
  no payment network involved and no real card data anywhere.
- `labcards.guard_target()` refuses any host outside `*.democuda.org`,
  `localhost` and `127.0.0.1`. `--force` overrides it and prints a warning.
  Only ever point these at systems you are authorised to test.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # tier 4 only
export LAB_SECRET=<the same value as the lab's .env>
```

`--secret` must match the target's `LAB_SECRET`. The dump generator uses it to
build *internally consistent* records — accurate expiry and CVV alongside each
PAN, the way a real stolen dump looks. It does not reveal which cards are live;
only submitting them tells you that, which is the entire point of carding.

## The tiers

| Script | Threat | Beats | Stopped by |
|---|---|---|---|
| `t1_blast.py` | OAT-001 | nothing | Brute Force Prevention |
| `t2_slowroll.py` | OAT-001 | rate limiting, form protection | Bot Protection (TLS fingerprint, UA analysis) |
| `t4_browser.py` | OAT-001 | JS challenges | Advanced Bot Protection (browser integrity, device velocity) |
| `t5_crack.py` | OAT-010 | — | Brute Force Prevention + URL-aware scoring |

### t1 — naive blast

No session, no referrer, maximum concurrency. What every unprotected form meets
first.

```bash
python3 t1_blast.py --target https://insecure.pay.democuda.org --count 500 --workers 16
```

### t2/t3 — session-aware slow roll

Browses first, keeps cookies, carries forward every hidden field the server or
WAF injects, rotates User-Agent, jitters its pacing, and stays under a plausible
rate limit. Demonstrates that rate limiting buys time rather than safety.

```bash
python3 t2_slowroll.py --target https://secure.pay.democuda.org --count 200 --rate 0.5
```

### t4 — headless browser

Real Chromium, so a JS challenge is solved automatically. What it cannot hide is
one device testing card after card.

```bash
python3 t4_browser.py --target https://secure.pay.democuda.org --count 50 --headed
```

Use `--headed` on a demo screen — watching the form fill itself lands better
than a scrolling log. `--cards-per-context 0` (the default) keeps a single
fingerprint for the whole run, which is the case device-level velocity should
catch.

### t5 — card cracking

One PAN, no expiry, no CVV. Because the app returns code 54 for a wrong expiry
and 82 for a wrong CVV, the search splits in two: at most 48 requests to find
the expiry, then at most 1,000 for the CVV. Roughly 520 on average against
48,000 for a naive sweep.

```bash
python3 t5_crack.py --target https://insecure.pay.democuda.org --pan 4111117066907437
```

Feed it a PAN that `t1_blast.py` already confirmed is live — a dead card returns
code 05 to everything and the script will say so and stop.

## Reading the output

Every tier prints the same scoreboard. The outcome vocabulary is what matters
once a WAF is in the path:

- `approved` — a live card was found. The attacker won this request.
- `declined:NN` — the form answered honestly. The attacker learned something.
- `blocked` — the WAF rejected the request. The mitigation is working.
- `challenge` — neither marker was present, usually a JS challenge or an
  interstitial. Also a win for the defence against a non-browser client.

A run that ends `blocked=500 approved=0` is the slide you want.

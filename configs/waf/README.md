# configs/waf — WaaS policy notes

Working notes for configuring the `secure.pay.democuda.org` application in
Barracuda WAF-as-a-Service, one rung of the demo ladder at a time.

These are **notes, not exported policy files**. WaaS has no portable policy
export that round-trips cleanly between tenants, and the console's menu layout
shifts between releases — treat the control names below as the thing to search
for rather than a literal click path. Verify against
[the WaaS documentation](https://documentation.campus.barracuda.com/wiki/display/WAFAAS/)
for your tenant's version.

## Application setup

| Setting | Value |
|---|---|
| Hostname | `secure.pay.democuda.org` |
| Origin | `20.102.125.204:8081`, plain HTTP |
| Host header | **Preserve** — Caddy routes on it, so rewriting breaks the origin |
| TLS | Terminated at WaaS |

The Azure NSG must allow `:8081` **only** from Barracuda WaaS source ranges. If
a prospect can reach the origin directly, the whole demo is arguable.

## Rung 0 — baseline

Everything off. Confirm all four attack tiers behave exactly as they do against
`insecure.pay.democuda.org`. This proves WaaS is in the path without yet doing
anything, and it is worth showing: it makes the later rungs obviously causal.

## Rung 1 — Brute Force Prevention

Target `POST /checkout`. Set a Count Window and a Block Threshold low enough
that `t1_blast.py` trips it in a couple of seconds — a few dozen requests per
minute per IP is realistic for a payment endpoint, where a genuine user submits
once or twice.

- **Stops:** `t1_blast.py`
- **Does not stop:** `t2_slowroll.py --rate 0.5`

Let the prospect watch tier 2 walk straight past it. The honest line is that
rate limiting raises the attacker's cost and buys investigation time; it does
not stop a patient bot.

## Rung 2 — Form Protection

Add Form Protection to `/checkout` under the application's profile. This adds
hidden-field and CSRF enforcement the app itself does not implement, so a bare
`POST` with no prior `GET` is rejected.

- **Stops:** any script that posts blind
- **Does not stop:** `t2_slowroll.py`, which fetches the form and carries every
  hidden field forward via `labcards.harvest_form_fields()`

Worth showing precisely because it fails against a competent bot. It closes the
lazy attack, not the real one.

## Rung 3 — Bot Protection

The rung that actually ends tier 2/3. With **Enable Advanced Bot Protection** set
to ON, the detection layers are enabled automatically and need no individual
tuning. The ones carrying this rung:

- **TLS Fingerprinting** — `requests` presents a TLS handshake no browser produces.
  This is why pacing does not save tier 2: the fingerprint is wrong at any speed.
- **User-Agent Analysis** — catches missing, anomalous or rotating UA strings.
- **Behavioral Pattern Detection** — device-level request rate, path diversity and
  referrer behaviour. A client that only ever touches `/checkout` has no funnel.
- **Header Analysis** — request headers against known automated-tool patterns.

Composite risk-score thresholds are set on the Risk Scores page; modules can
block at device level or IP level.

- **Stops:** `t1_blast.py`, `t2_slowroll.py`
- **Does not stop:** `t4_browser.py`

## Rung 4 — Advanced Bot Protection against a real browser

Same switch, different layers doing the work:

- **Browser Integrity Verification** — validates client-side signals to detect
  headless browsers and automation frameworks. This is what sees Playwright.
- **Behavioral Pattern Detection** at device level — one fingerprint submitting
  dozens of distinct PANs is not a shopper.
- **URL-Aware Scoring** — context-aware risk evaluation on sensitive URL
  categories, which is where a payment endpoint belongs.

**Requires an Advanced Bot Protection licence.** Confirm the tenant's
entitlement before promising this rung in front of a prospect. Without it, the
demo honestly ends at rung 3 — which is still a strong story, just not the
complete one.

- **Stops:** `t4_browser.py`

## Rung 5 — card cracking

Point `t5_crack.py` at the protected host. Brute Force Prevention and URL-aware
scoring both bite here because the velocity against a single parameter set is
extreme.

Then make the developer point, because this is the one the WAF only half-owns:
the app hands back a different decline code for a wrong expiry than for a wrong
CVV, and that is what reduces the search from 48,000 requests to 1,048. A WAF
can throttle the attempts. Only a developer can stop the form from narrating
which field was wrong.

That distinction — what the WAF fixes today versus what belongs in the
application backlog — is the most credible thing an SA can say in this demo.

# SA demo script — carding

A 20–25 minute live demo. The narrative is an escalation ladder: the attacker
adapts, the defence tightens, and the prospect watches each control get defeated
until bot fingerprinting ends it.

Do not open with "here is our WAF, watch it block things." Open with the loss.

## Before the room

- [ ] `make up` and confirm both instances answer `/healthz`
- [ ] `make reset` to zero both dashboards
- [ ] WaaS rungs 1–4 configured but **disabled** (see `../configs/waf/README.md`)
- [ ] `export LAB_SECRET=<value from .env>` in the attack shell
- [ ] Pre-run `t1_blast.py` once against the insecure host and keep a live PAN
      for the tier 5 segment — cracking a card you already know is live avoids
      dead air
- [ ] Raise `LIVE_RATE` to 10 in `.env` if you want hits to land fast on screen
- [ ] Confirm ABP entitlement if you intend to show rung 4

## Screen layout

Three panes, left to right:

1. Terminal running the attack
2. `https://insecure.pay.democuda.org/ops` — the victim's dashboard
3. The WaaS console

The dashboard is the one the prospect should be watching. The hero number is
**live cards found**; that is the number that costs their customer money.

---

## Act 1 — the loss (4 min)

Walk the normal funnel in a browser first: product page, checkout, pay with a
card. One approval. "This is your form. It works."

Then:

```bash
python3 t1_blast.py --target https://insecure.pay.democuda.org --count 500 --workers 16
```

Say nothing for the first few seconds. Let them watch the dashboard counter run.

Five hundred cards in under two seconds, and the live-cards panel fills with
chargeable numbers. Land the point: **the form answered 500 questions for free.**
Each APPROVED is a card the attacker now sells or cashes out, and every attempt
is an authorisation the issuer sees — which is where the chargeback fees and the
acquirer's attention come from, even for the declines.

Ask what their current control is. The answer is usually "we rate limit."

## Act 2 — rate limiting is not enough (5 min)

Enable **rung 1, Brute Force Prevention**. Re-run tier 1 against the secure host.
It dies — `blocked=500 approved=0`.

Then, before they get comfortable:

```bash
python3 t2_slowroll.py --target https://secure.pay.democuda.org --count 200 --rate 0.5
```

It walks straight through. Browses first, keeps cookies, rotates User-Agent,
jitters its pacing, stays under the threshold.

This is the most important beat in the demo and the one that earns trust:

> Rate limiting is worth having. It raises the attacker's cost and buys you time
> to notice. It does not stop a patient bot, and anyone selling it to you as a
> carding fix is overselling.

Optionally show **rung 2, Form Protection** here. It closes the blind `POST` and
tier 2 shrugs it off, because the script parses the form and carries the hidden
fields forward. Same lesson, reinforced.

## Act 3 — the control that works (6 min)

Enable **rung 3, Bot Protection**. Re-run tier 2 unchanged.

Dead on the first request. Explain why, because this is the technical substance:

- Its TLS handshake is `requests`, not a browser. Pacing cannot fix a
  fingerprint.
- It has no browsing funnel — it only ever touches `/checkout`.
- Its headers do not match the browser it claims to be.

The attacker's whole tier-2 strategy was "look patient." The WAF is not looking
at patience.

## Act 4 — the attacker escalates (5 min)

*Requires the ABP licence. Skip cleanly if the tenant lacks it.*

```bash
python3 t4_browser.py --target https://secure.pay.democuda.org --count 50 --headed
```

Let them watch a real Chromium fill the form by itself. The JS challenge is
solved, because this genuinely is a browser.

It still loses — browser integrity verification spots the automation framework,
and device-level velocity sees one fingerprint testing fifty distinct PANs. Make
the licensing distinction explicit and honest: base Bot Protection handled the
scripted attacker, and this rung is what the add-on buys.

## Act 5 — what the WAF cannot fix (4 min)

Back to the unprotected host:

```bash
python3 t5_crack.py --target https://insecure.pay.democuda.org --pan <known live PAN>
```

One card, no expiry, no CVV. It recovers both in roughly 500 requests. Show the
tally: a run of code 54s, then the flip to 82, then the approval.

Brute-forcing both fields blindly is 48,000 requests. The form cut that by
roughly 45x **by telling the attacker which field was wrong.**

Enable brute-force protection on the secure host and show the run getting cut
off. Then be straight about the limit of what you just sold them:

> We throttled it. We did not fix it. As long as the form returns a different
> error for a bad expiry than for a bad CVV, the attack stays cheap for anyone
> who gets past us. That one is a developer ticket, and it should be in your
> next sprint regardless of what you buy from me.

## Close

Three things to leave in the room:

1. **Carding is an availability and cost problem, not just fraud.** Declines
   carry fees and put their acquirer relationship at risk.
2. **Rate limiting alone does not solve it.** They watched that fail.
3. **Bot detection is the control that matters**, and the response detail is a
   developer fix no WAF owns.

The honest ladder is what makes this credible. A demo that claims the WAF fixes
everything invites the one objection you cannot answer.

---

## Reset between runs

```bash
make reset
```

Or the **Reset counters** button on either `/ops` page.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Everything returns code 05 | `--secret` does not match the target's `LAB_SECRET` |
| Zero approvals in a 500-card run | `LIVE_RATE` is low; raise it in `.env` and recreate the containers |
| `challenge` on every attempt | A JS challenge is active — expected at rung 3+ |
| Dashboard frozen | SSE dropped; reload. Counters are server-side and intact |
| Tier 5 only ever returns 05 | The PAN is not live. Use one tier 1 confirmed |
| Caddy has no certificate | AWS Route53 credentials missing or wrong in `.env` |

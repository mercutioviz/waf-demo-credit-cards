"""Fake card issuer.

Nothing here reaches a real payment network. A card's liveness, expiry and CVV
are all derived deterministically from HMAC-SHA256(LAB_SECRET, PAN). That makes
a demo repeatable across container restarts while keeping every result
meaningless outside this lab.
"""

import hashlib
import hmac

APPROVED = "00"
DECLINE_INVALID_NUMBER = "14"
DECLINE_DO_NOT_HONOUR = "05"
DECLINE_EXPIRED_CARD = "54"
DECLINE_INVALID_CVV = "82"

MESSAGES = {
    APPROVED: "Approved",
    DECLINE_INVALID_NUMBER: "Invalid card number",
    DECLINE_DO_NOT_HONOUR: "Do not honour",
    DECLINE_EXPIRED_CARD: "Expired card",
    DECLINE_INVALID_CVV: "Invalid security code",
}


def digits_only(value):
    return "".join(c for c in (value or "") if c.isdigit())


def luhn_ok(pan):
    digits = [int(c) for c in pan]
    if len(digits) < 12:
        return False
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def mask_pan(pan):
    if len(pan) < 10:
        return "*" * len(pan)
    return f"{pan[:6]}{'*' * (len(pan) - 10)}{pan[-4:]}"


class Issuer:
    def __init__(self, secret, live_rate):
        self._secret = secret.encode()
        # First digest byte is uniform over 0-255, so scaling the threshold by
        # the requested percentage gives roughly that share of live cards.
        self._threshold = max(1, round(255 * live_rate / 100.0))

    def _digest(self, pan):
        return hmac.new(self._secret, pan.encode(), hashlib.sha256).digest()

    def is_live(self, pan):
        return self._digest(pan)[0] < self._threshold

    def expected_credentials(self, pan):
        """The expiry and CVV this issuer considers correct for a PAN.

        A real stolen dump carries accurate expiry and CVV alongside the number,
        so the dump generator in attack/labcards.py reproduces this derivation.
        Card cracking (tier 5) is the case where the attacker does not have them.
        """
        digest = self._digest(pan)
        month = digest[1] % 12 + 1
        year = 26 + digest[2] % 4
        cvv = int.from_bytes(digest[3:5], "big") % 1000
        return f"{month:02d}", f"{year:02d}", f"{cvv:03d}"

    def authorize(self, pan, exp_month, exp_year, cvv):
        """Return (approved, code).

        Order matters. Checking expiry before CVV, and returning a different
        code for each, is the deliberate oracle that makes tier-5 card cracking
        cheap: it splits a 48,000-request search into 48 + 1,000.
        """
        pan = digits_only(pan)
        if not luhn_ok(pan):
            return False, DECLINE_INVALID_NUMBER
        if not self.is_live(pan):
            return False, DECLINE_DO_NOT_HONOUR

        want_month, want_year, want_cvv = self.expected_credentials(pan)
        got_month = digits_only(exp_month).zfill(2)
        got_year = digits_only(exp_year)[-2:]
        if (got_month, got_year) != (want_month, want_year):
            return False, DECLINE_EXPIRED_CARD
        if digits_only(cvv) != want_cvv:
            return False, DECLINE_INVALID_CVV
        return True, APPROVED

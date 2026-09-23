"""Phone number validation/normalization for demo WhatsApp contacts. Uses Google's libphonenumber
(the `phonenumbers` package - MIT licensed, the standard mature library for this problem) rather than
inventing international numbering-plan rules ourselves - see docs/architecture/integrations/
WHATSAPP_DEMO_TRANSPORT_COMPARISON.md and CLAUDE.md's OSS-first rule.

Not India-specific: `DEFAULT_REGION` only resolves a number that carries NO explicit country code at
all (e.g. a bare 10-digit Indian mobile) - any number with a country code (`+91...`, `+1...`, etc.) is
parsed correctly regardless of the caller's region, exactly as libphonenumber is designed to work
worldwide.
"""

from __future__ import annotations

import phonenumbers

DEFAULT_REGION = "IN"  # only used when the input carries no country code at all


class PhoneValidationError(ValueError):
    """Raised for anything that is not a real, dialable phone number - never silently accepted just
    because it happens to be all-digits of some length."""


def normalize_phone(raw: str, *, default_region: str = DEFAULT_REGION) -> str:
    """Returns a canonical digits-only E.164-minus-the-plus string (e.g. "919825133222"), matching
    this codebase's existing DemoSessionContact.phone_e164 / WAHA chatId convention. Raises
    PhoneValidationError - never returns something unvalidated - for anything that is not a real,
    valid, dialable number: too short, too long, wrong-shaped for its claimed country code, non-numeric,
    or blank."""
    if not raw or not raw.strip():
        raise PhoneValidationError("phone number is required")
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise PhoneValidationError(f"'{raw}' does not look like a phone number ({exc})") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise PhoneValidationError(f"'{raw}' is not a valid, dialable phone number")
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return e164.lstrip("+")

"""Text, phone and URL normalisation helpers.

Deliberately dependency-free (no `frappe` import) so the same functions run inside
a web request, inside a background job, in tests, and in a plain REPL.
"""

from __future__ import annotations

import re
import unicodedata

DEFAULT_CC = "255"  # Tanzania

_COMPANY_SUFFIXES = [
    "co ltd", "company limited", "company ltd", "limited", "ltd", "plc", "llc", "inc",
    "incorporated", "corporation", "corp", "gmbh", "sa", "bv", "holdings", "holding",
    "group of companies", "group", "enterprises", "enterprise", "traders", "trading",
    "tanzania", "tz", "and sons", "& sons", "sons", "brothers", "bros",
]

_PUNCT_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def squash(text: str) -> str:
    """lowercase, remove accents + punctuation, collapse whitespace."""
    if not text:
        return ""
    text = strip_accents(str(text)).lower().replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def normalize_company_name(name: str) -> str:
    """'Kilimanjaro Foods (T) Ltd.' -> 'kilimanjaro foods'"""
    text = squash(name)
    if not text:
        return ""
    if text.startswith("the "):
        text = text[4:].strip()
    changed = True
    while changed:
        changed = False
        for suffix in _COMPANY_SUFFIXES:
            if text == suffix:
                continue
            if text.endswith(" " + suffix):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
    return _SPACE_RE.sub(" ", text).strip()


def normalize_phone(raw, default_cc: str = DEFAULT_CC) -> str:
    """Return an E.164-ish string (+255754123456) or '' when the input cannot be normalised.

    Handles the shapes that actually appear in Tanzanian business data:
      +255 754 123 456 / 00255754123456 / 255754123456 / 0754123456 / 754123456
      (022) 211 2345  -> landline
    """
    if raw is None:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""
    cc = re.sub(r"\D", "", str(default_cc or DEFAULT_CC))

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith(cc) and len(digits) > len(cc):
        return "+" + digits
    if digits.startswith("0"):
        return "+" + cc + digits[1:]
    if len(digits) == 9:  # 754123456 (mobile without leading 0)
        return "+" + cc + digits
    if len(digits) in (10, 11):  # 0221234567 style landline
        if digits.startswith("0"):
            return "+" + cc + digits[1:]
    if len(digits) >= 11:
        return "+" + digits
    return ""


def normalize_email(raw) -> str:
    if not raw:
        return ""
    email = str(raw).strip().lower()
    if "@" not in email or " " in email:
        return ""
    return email


def domain_from_website(raw) -> str:
    """'https://www.kilimanjaro.co.tz/about' -> 'kilimanjaro.co.tz'"""
    if not raw:
        return ""
    text = str(raw).strip().lower()
    text = re.sub(r"^[a-z]+://", "", text)
    text = text.split("/")[0].split("?")[0]
    text = text.split("@")[-1]
    text = re.sub(r"^www\.", "", text)
    if "." not in text:
        return ""
    return text


def whatsapp_link(phone: str, message: str = "") -> str:
    """Build a wa.me link from a normalised phone."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if not digits:
        return ""
    from urllib.parse import quote

    base = f"https://wa.me/{digits}"
    if message:
        base += f"?text={quote(message)}"
    return base


def employee_band(count) -> str:
    try:
        n = int(count)
    except (TypeError, ValueError):
        return ""
    if n <= 10:
        return "1-10"
    if n <= 50:
        return "11-50"
    if n <= 200:
        return "51-200"
    return "200+"


def band_bounds(band: str):
    """'11-50' -> (11, 50); '200+' -> (200, None)"""
    if not band:
        return (None, None)
    if band.endswith("+"):
        return (int(band[:-1]), None)
    if "-" in band:
        lo, hi = band.split("-", 1)
        try:
            return (int(lo), int(hi))
        except ValueError:
            return (None, None)
    return (None, None)


def pct(numerator, denominator, ndigits: int = 1):
    try:
        if not denominator:
            return 0.0
        return round(100.0 * float(numerator) / float(denominator), ndigits)
    except (TypeError, ValueError):
        return 0.0

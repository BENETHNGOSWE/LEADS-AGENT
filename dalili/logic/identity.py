"""Entity resolution: is this company the same company as that one?

Tanzanian companies appear under many spellings across BRELA, Google, Facebook,
Instagram, tender records and invoices. Getting this right is the core asset of the
product, so the logic lives here, is deterministic, and is unit-tested.
"""

from __future__ import annotations

import difflib
import re

from dalili.logic.normalize import (
    domain_from_website,
    normalize_company_name,
    normalize_phone,
    squash,
)

# Preference order for building a match key. The first available identifier wins,
# because it is the most stable/predictable identifier for that entity.
KEY_PRECEDENCE = ("brela_number", "tin", "domain", "phone", "name")

_STOPWORDS = {
    "the", "and", "of", "for", "a", "an", "in", "on", "at", "to", "tz", "tanzania",
}


def _tokenise(name: str) -> list[str]:
    text = normalize_company_name(name)
    return [t for t in text.split(" ") if t and t not in _STOPWORDS]


def _initials(raw_name: str) -> str:
    """Initials of every word in the raw name, so 'KFL' matches
    'Kilimanjaro Foods Limited' even though 'limited' is stripped elsewhere."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", raw_name or "")
    return "".join(w[0].lower() for w in words)


def similarity(a: str, b: str) -> float:
    """0..1 similarity of two company names, tolerant of word order and suffixes."""
    ta, tb = _tokenise(a), _tokenise(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0

    joined_a, joined_b = " ".join(ta), " ".join(tb)
    ratio = difflib.SequenceMatcher(None, joined_a, joined_b).ratio()

    set_a, set_b = set(ta), set(tb)
    jaccard = len(set_a & set_b) / max(1, len(set_a | set_b))
    subset = 1.0 if (set_a <= set_b or set_b <= set_a) else 0.0

    # An acronym match ("KFL" vs "Kilimanjaro Foods Limited") is a strong hint.
    acronym_hit = 0.0
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(shorter) == 1 and len(shorter[0]) >= 2:
        token_initials = "".join(t[0] for t in longer)
        raw_initials = _initials(b if len(ta) <= len(tb) else a)
        candidate = shorter[0]
        for initials in (token_initials, raw_initials):
            if initials and (candidate == initials or initials.startswith(candidate)):
                acronym_hit = 0.9
                break

    return round(max(ratio, jaccard, subset * 0.85, acronym_hit), 4)


def match_key(*, brela_number=None, tin=None, domain=None, phone=None, name=None,
              default_cc: str = "255") -> str:
    """Build the deterministic uniqueness key used by the Dalili Prospect DocType."""
    brela = squash(str(brela_number or ""))
    if brela:
        return f"brela:{brela}"

    tax = squash(str(tin or ""))
    if tax:
        return f"tin:{tax}"

    dom = squash(domain_from_website(domain) or domain)
    if dom:
        return f"domain:{dom}"

    tel = normalize_phone(phone, default_cc)
    if tel:
        # Only use a phone as identity when it is a real E.164 number.
        return f"phone:{tel}"

    norm = normalize_company_name(name or "")
    if norm:
        return f"name:{norm}"
    return ""


def candidate_from_mapping(row: dict) -> dict:
    """Normalise a loose dict (API payload, CSV row, provider result) into identifiers."""
    return {
        "name": row.get("company_name") or row.get("name") or "",
        "brela_number": row.get("brela_number") or "",
        "tin": row.get("tin") or "",
        "domain": row.get("domain") or domain_from_website(row.get("website") or ""),
        "phone": row.get("primary_phone") or row.get("phone") or "",
    }


def find_duplicate(candidate: dict, existing: list[dict], threshold: float = 0.88):
    """Return (index, score, reason) of the best existing match, or (None, 0.0, '')."""
    cand = candidate_from_mapping(candidate)
    cand_key = match_key(**cand)

    best_idx, best_score, best_reason = None, 0.0, ""

    for idx, row in enumerate(existing):
        other = candidate_from_mapping(row)
        other_key = match_key(**other)

        if cand_key and cand_key == other_key:
            return idx, 1.0, f"identical key {cand_key}"

        # Explicit identifier collisions are decisive even if names differ.
        for field in ("brela_number", "tin"):
            if cand.get(field) and other.get(field):
                if squash(cand[field]) == squash(other[field]):
                    return idx, 1.0, f"same {field}"

        if cand.get("domain") and other.get("domain") and cand["domain"] == other["domain"]:
            return idx, 1.0, "same domain"

        phone_a = normalize_phone(cand.get("phone"))
        phone_b = normalize_phone(other.get("phone"))
        if phone_a and phone_a == phone_b:
            return idx, 0.99, "same phone"

        name_score = similarity(cand.get("name", ""), other.get("name", ""))
        score, reason = name_score, "name similarity"
        # Corroborate a fuzzy name hit with any shared identifier for a safer merge.
        if name_score >= 0.7:
            if cand.get("domain") and cand["domain"] == other.get("domain"):
                score, reason = min(0.99, name_score + 0.2), "name + domain"
            elif phone_a and phone_a == phone_b:
                score, reason = min(0.99, name_score + 0.2), "name + phone"

        if score > best_score:
            best_idx, best_score, best_reason = idx, score, reason

    if best_idx is not None and best_score >= threshold:
        return best_idx, round(best_score, 4), best_reason
    return None, 0.0, ""


def _is_blank(value) -> bool:
    return value in (None, "", 0, "0")


def merge_into(primary: dict, secondary: dict, *, prefer_verified: bool = True) -> dict:
    """Fill blanks in `primary` from `secondary`. Never overwrites an existing value,
    except that a verified value beats an unverified one."""
    merged = dict(primary)
    for key, value in secondary.items():
        if _is_blank(value):
            continue
        if _is_blank(merged.get(key)):
            merged[key] = value
            continue
        if prefer_verified:
            if str(key).startswith("verified_") and not merged.get(key):
                merged[key] = value
    return merged


def dedupe_batch(rows: list[dict], threshold: float = 0.88) -> tuple[list[dict], int]:
    """Deduplicate a freshly discovered batch. Returns (unique_rows, merge_count)."""
    unique: list[dict] = []
    merges = 0
    for row in rows:
        idx, score, _reason = find_duplicate(row, unique, threshold=threshold)
        if idx is None:
            unique.append(dict(row))
        else:
            unique[idx] = merge_into(unique[idx], row)
            merges += 1
    return unique, merges


def name_tokens(name: str) -> list[str]:
    return _tokenise(name)


PHONE_LIKE = re.compile(r"^\+?\d{9,15}$")

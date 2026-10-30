"""Explainable lead scoring.

Every score is decomposed into named components so a sales manager can see *why* a
company is ranked where it is. A black-box number is unsellable in this market.

All functions are pure: they take plain dicts and return plain dicts, and accept an
optional `today` (date/datetime) so results are reproducible in tests.
"""

from __future__ import annotations

import math
from datetime import date, datetime

from dalili.logic.normalize import band_bounds, normalize_company_name, squash

DEFAULT_WEIGHTS = {
    "fit": 35.0,
    "signal": 30.0,
    "confidence": 20.0,
    "contactability": 15.0,
}

SENIORITY_RANK = {
    "Owner / Founder": 1.0,
    "C-Level": 0.95,
    "Director": 0.85,
    "Manager": 0.7,
    "Officer": 0.5,
    "Unknown": 0.25,
}


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
            try:
                return datetime.strptime(value[:19], fmt).date()
            except ValueError:
                continue
    return None


def _token_list(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [squash(str(x)) for x in raw if str(x).strip()]
    return [squash(x) for x in str(raw).replace(";", ",").split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def fit_score(prospect: dict, icp: dict) -> dict:
    """How well does this company match the ideal-customer profile?

    Fit is the *share of the criteria the user actually stated* that this company
    meets — not a fixed tally. That distinction matters: an ICP with three filters
    that all match should read 100, exactly like an ICP with six filters that all
    match. Earlier the weights simply added up, so a perfect three-filter match
    topped out at 78 and no lead could ever be HOT on fit alone.

    Returns {"score": 0-100, "reasons": [...], "excluded": bool}
    """
    reasons: list[str] = []
    earned = 0.0
    available = 0.0
    haystack = squash(
        " ".join(
            str(prospect.get(k) or "")
            for k in ("company_name", "legal_name", "sub_sector", "notes", "website")
        )
    )

    # Hard exclusions first — an excluded company scores zero, full stop.
    for kw in _token_list(icp.get("exclude_keywords")):
        if kw and kw in haystack:
            return {"score": 0.0, "reasons": [f"excluded by keyword '{kw}'"], "excluded": True}

    sector = (icp.get("sector") or "").strip()
    if sector:
        available += 40
        if squash(prospect.get("sector") or "") == squash(sector):
            earned += 40
            reasons.append(f"sector match ({sector})")
        else:
            earned += 8
            reasons.append("sector mismatch")

    region = (icp.get("region") or "").strip()
    if region:
        available += 20
        if squash(prospect.get("region") or "").startswith(squash(region)):
            earned += 20
            reasons.append(f"in {region}")
        else:
            reasons.append(f"outside {region}")

    district = (icp.get("district") or "").strip()
    if district:
        available += 8
        if squash(district) in squash(
            " ".join(str(prospect.get(k) or "") for k in ("district", "ward", "address"))
        ):
            earned += 8
            reasons.append(f"in {district}")
        else:
            reasons.append(f"outside {district}")

    lo = icp.get("employee_band_min")
    hi = icp.get("employee_band_max")
    if lo or hi:
        available += 18
        b_lo, b_hi = band_bounds(prospect.get("employee_band") or "")
        if b_lo is not None:
            ok = True
            if lo and b_hi is not None and b_hi < int(lo):
                ok = False
            if hi and b_lo > int(hi):
                ok = False
            if ok:
                earned += 18
                reasons.append("size in range")
            else:
                reasons.append("size out of range")
        else:
            reasons.append("size unknown")

    band = (icp.get("revenue_band") or "").strip()
    if band:
        available += 8
        if squash(prospect.get("revenue_band") or "") == squash(band):
            earned += 8
            reasons.append("revenue band match")
        else:
            reasons.append("revenue band mismatch")

    include = _token_list(icp.get("include_keywords"))
    if include:
        available += 20
        hits = [kw for kw in include if kw and kw in haystack]
        if hits:
            earned += min(20, 10 * len(hits))
            reasons.append(f"keyword hit: {', '.join(hits[:3])}")
        else:
            earned -= 10
            reasons.append("required keyword missing")

    founded_after = icp.get("founded_after")
    if founded_after:
        available += 5
        try:
            if int(prospect.get("founded_year") or 0) >= int(founded_after):
                earned += 5
                reasons.append("recently founded")
            else:
                reasons.append("established before cutoff")
        except (TypeError, ValueError):
            pass

    if available <= 0:
        # No criteria stated: fit cannot discriminate, so stay neutral and let
        # signals and contactability do the ranking.
        return {"score": 70.0, "reasons": ["no fit criteria given (neutral)"], "excluded": False}

    score = 100.0 * max(0.0, earned) / available
    return {"score": round(min(100.0, score), 2), "reasons": reasons, "excluded": False}


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
def signal_score(signals: list[dict], *, decay_days: int = 90, saturation: float = 40.0,
                 today=None) -> dict:
    """Time-decayed buying-signal strength, normalised to 0-100.

    A signal with `strength` 15 detected today contributes 15 raw points; the same
    signal 90 days old contributes ~5.5 (exponential decay).
    """
    today = _as_date(today) or date.today()
    decay_days = max(1, int(decay_days or 90))
    raw_total = 0.0
    considered = []

    for sig in signals or []:
        try:
            strength = float(sig.get("strength") or 0)
        except (TypeError, ValueError):
            strength = 0.0
        if strength <= 0:
            continue
        detected = _as_date(sig.get("detected_on")) or today
        age = max(0, (today - detected).days)
        factor = math.exp(-age / decay_days)
        contribution = strength * factor
        raw_total += contribution
        considered.append(
            {
                "title": sig.get("title") or sig.get("signal_type") or "signal",
                "age_days": age,
                "factor": round(factor, 3),
                "contribution": round(contribution, 2),
            }
        )

    score = 0.0
    if saturation > 0:
        score = min(100.0, 100.0 * raw_total / float(saturation))

    considered.sort(key=lambda s: s["contribution"], reverse=True)
    return {
        "score": round(score, 2),
        "raw": round(raw_total, 2),
        "signals": considered[:5],
    }


# ---------------------------------------------------------------------------
# Data confidence
# ---------------------------------------------------------------------------
def confidence_score(source_refs: list[dict], *, today=None, stale_days: int = 365) -> dict:
    """How much do we trust this record? Source reliability x recency + multi-source bonus."""
    today = _as_date(today) or date.today()
    if not source_refs:
        return {"score": 0.0, "sources": 0, "reasons": ["no sources recorded"]}

    weighted, weight_sum, independent = 0.0, 0.0, set()
    for ref in source_refs:
        try:
            conf = float(ref.get("confidence") or 60)
        except (TypeError, ValueError):
            conf = 60.0
        retrieved = _as_date(ref.get("retrieved_on")) or today
        age = max(0, (today - retrieved).days)
        recency = max(0.35, math.exp(-age / max(1, stale_days)) )
        weighted += conf * recency
        weight_sum += recency
        independent.add(squash(ref.get("source_label") or ref.get("source_type") or ref.get("source") or "unknown"))

    base = weighted / weight_sum if weight_sum else 0.0
    bonus = min(15.0, 5.0 * max(0, len(independent) - 1))
    reasons = [f"{len(independent)} independent source(s)"]
    if bonus:
        reasons.append(f"+{bonus:.0f} multi-source bonus")
    return {"score": round(min(100.0, base + bonus), 2), "sources": len(independent),
            "reasons": reasons}


# ---------------------------------------------------------------------------
# Contactability
# ---------------------------------------------------------------------------
def contactability_score(contacts: list[dict]) -> dict:
    """Can we actually reach a human at this company, today?"""
    if not contacts:
        return {"score": 0.0, "reasons": ["no contacts"], "best": None}

    best_value, best_contact = -1.0, None
    for c in contacts:
        if c.get("do_not_contact"):
            continue
        value = 0.0
        status = (c.get("verification_status") or "").strip()
        verified = status == "Verified"
        # A verified reachable channel is the whole point of this component.
        if c.get("whatsapp"):
            value += 50 if verified else 25
        if c.get("phone"):
            value += 25 if verified else 12
        if c.get("email"):
            value += 10 if verified else 5
        value += 20 * SENIORITY_RANK.get(c.get("seniority") or "Unknown", 0.25)
        if (c.get("consent_basis") or "") not in ("", "Unknown"):
            value += 5
        if value > best_value:
            best_value, best_contact = value, c

    if best_contact is None:
        return {"score": 0.0, "reasons": ["all contacts opted out"], "best": None}

    reasons = []
    if best_contact.get("whatsapp"):
        reasons.append("WhatsApp available")
    if (best_contact.get("verification_status") or "") == "Verified":
        reasons.append("contact verified")
    reasons.append(f"seniority: {best_contact.get('seniority') or 'Unknown'}")
    return {
        "score": round(min(100.0, max(0.0, best_value)), 2),
        "reasons": reasons,
        "best": best_contact.get("name") or best_contact.get("full_name"),
    }


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
def normalise_weights(weights: dict | None) -> dict:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        for key in w:
            try:
                if weights.get(key) is not None:
                    w[key] = float(weights[key])
            except (TypeError, ValueError):
                pass
    total = sum(v for v in w.values() if v > 0)
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: (v / total) * 100.0 for k, v in w.items()}


def score_prospect(prospect: dict, icp: dict, *, contacts=None, signals=None,
                   sources=None, weights=None, decay_days=90, today=None) -> dict:
    """Full explainable score. Returns components, weights and the total."""
    fit = fit_score(prospect, icp)
    if fit["excluded"]:
        return {
            "total": 0.0,
            "excluded": True,
            "components": {"fit": 0.0, "signal": 0.0, "confidence": 0.0, "contactability": 0.0},
            "weights": normalise_weights(weights),
            "reasons": {"fit": fit["reasons"], "signal": [], "confidence": [], "contactability": []},
        }

    sig = signal_score(signals or [], decay_days=decay_days, today=today)
    conf = confidence_score(sources or [], today=today)
    cont = contactability_score(contacts or [])
    w = normalise_weights(weights)

    total = (
        fit["score"] * w["fit"]
        + sig["score"] * w["signal"]
        + conf["score"] * w["confidence"]
        + cont["score"] * w["contactability"]
    ) / 100.0

    return {
        "total": round(total, 2),
        "excluded": False,
        "components": {
            "fit": fit["score"],
            "signal": sig["score"],
            "confidence": conf["score"],
            "contactability": cont["score"],
        },
        "weights": {k: round(v, 2) for k, v in w.items()},
        "reasons": {
            "fit": fit["reasons"],
            "signal": [s["title"] for s in sig["signals"]],
            "confidence": conf["reasons"],
            "contactability": cont["reasons"],
        },
        "best_contact": cont.get("best"),
        "signal_raw": sig["raw"],
    }


def why_now(prospect: dict, signals: list[dict], *, today=None, limit: int = 2) -> str:
    """One-sentence reason to call this company this week (used on lead cards)."""
    today = _as_date(today) or date.today()
    ranked = []
    for sig in signals or []:
        detected = _as_date(sig.get("detected_on")) or today
        age = max(0, (today - detected).days)
        try:
            strength = float(sig.get("strength") or 0)
        except (TypeError, ValueError):
            strength = 0.0
        ranked.append((strength * math.exp(-age / 90.0), sig, age))
    ranked.sort(key=lambda x: x[0], reverse=True)

    parts = []
    for _value, sig, age in ranked[:limit]:
        title = (sig.get("title") or "").strip()
        if not title:
            continue
        when = "today" if age == 0 else f"{age}d ago"
        parts.append(f"{title} ({when})")
    if parts:
        return "; ".join(parts) + "."
    return f"No recent trigger found — {prospect.get('sector') or 'general'} fit only."

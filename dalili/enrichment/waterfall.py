"""The enrichment waterfall.

Why a waterfall: no single Tanzanian data source is good. Google has phones but no
sector or size; the registry has legal identity but no contacts; trade data has
purchasing behaviour but no addresses. Rather than trusting one database (the
Apollo model, which is 40-60% coverage and stale), query sources in priority order
and stop as soon as the field is filled — the Clay model, which reaches 85-95%
coverage.

Each successful fill is recorded as a `Dalili Source Ref` so every field on a
prospect can be traced to where it came from and when.
"""

from __future__ import annotations

import frappe

from dalili.logic.normalize import normalize_phone

# Fields we try to fill, in the order the waterfall attempts them.
ENRICHABLE_FIELDS = (
    "primary_phone",
    "primary_email",
    "website",
    "domain",
    "employee_band",
    "region",
    "district",
    "sector",
)


def _is_blank(value) -> bool:
    return value in (None, "", 0, "0")


def enrich_record(record: dict, providers, *, required=None) -> tuple[dict, list[dict], dict]:
    """Run the waterfall over one record.

    Returns (record, source_refs, stats) where stats has calls/cost/providers_used.
    """
    required = list(required or ("primary_phone", "primary_email", "website"))
    enriched = dict(record)
    source_refs: list[dict] = []
    stats = {"calls": 0, "cost": 0.0, "providers_used": [], "errors": []}

    # Record the discovery source first, so a record is never sourceless.
    if record.get("source_label"):
        source_refs.append(
            {
                "source_label": record.get("source_label"),
                "source_type": record.get("source_type") or "",
                "confidence": record.get("confidence") or 60,
                "retrieved_on": frappe.utils.now_datetime(),
                "source_id": record.get("source_id") or "",
                "url": record.get("source_url") or "",
                "excerpt": "discovery record",
            }
        )

    def filled_all() -> bool:
        return all(not _is_blank(enriched.get(f)) for f in required)

    if filled_all():
        return enriched, source_refs, stats

    for provider in providers or []:
        if filled_all():
            break
        if getattr(provider, "source_type", "") == "LLM Research":
            continue  # never let a model supply facts

        try:
            result = provider.enrich(enriched)
        except Exception as exc:  # a provider must never break the run
            stats["errors"].append(f"{provider.source_name}: {exc}")
            continue

        stats["calls"] += result.calls
        stats["cost"] += result.cost
        if result.error:
            stats["errors"].append(f"{provider.source_name}: {result.error}")
            continue

        for payload in result.records:
            changed = False
            for field in ENRICHABLE_FIELDS:
                value = payload.get(field)
                if _is_blank(value) or not _is_blank(enriched.get(field)):
                    continue
                if field == "primary_phone":
                    value = normalize_phone(value)
                    if not value:
                        continue
                enriched[field] = value
                changed = True
            if changed and provider.source_name not in stats["providers_used"]:
                stats["providers_used"].append(provider.source_name)
                source_refs.append(
                    {
                        "source_label": provider.source_name,
                        "source_type": getattr(provider, "source_type", ""),
                        "confidence": payload.get("confidence")
                        or getattr(provider, "options", {}).get("reliability")
                        or 60,
                        "retrieved_on": frappe.utils.now_datetime(),
                        "excerpt": "enrichment fill",
                    }
                )

    return enriched, source_refs, stats


def discover(filters: dict, providers, *, limit: int = 200) -> tuple[list[dict], dict]:
    """Query providers for candidate companies.

    Discovery providers are queried in priority order and results are concatenated
    (not waterfalled) because duplicates across sources are valuable — they raise
    the confidence score once the entity-resolution step merges them.
    """
    records: list[dict] = []
    stats = {"calls": 0, "cost": 0.0, "errors": [], "providers": []}

    for provider in providers or []:
        if getattr(provider, "source_type", "") == "LLM Research":
            continue
        try:
            result = provider.search(filters, limit=limit)
        except Exception as exc:
            stats["errors"].append(f"{provider.source_name}: {exc}")
            continue
        stats["calls"] += result.calls
        stats["cost"] += result.cost
        if result.error:
            stats["errors"].append(f"{provider.source_name}: {result.error}")
            continue
        if result.records:
            stats["providers"].append(provider.source_name)
            for record in result.records:
                record.setdefault("source_label", provider.source_name)
                record.setdefault("source_type", getattr(provider, "source_type", ""))
            records.extend(result.records)

    return records, stats

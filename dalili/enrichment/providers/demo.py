"""Demo provider — lets the whole product run with zero API keys and zero network.

This is what makes the app testable locally. It serves the synthetic universe in
`demo_pool.py`, filtered by the ICP, and simulates imperfect real-world data
(some records missing a website, some missing WhatsApp, some stale) so the
enrichment waterfall, scoring and verification flows all have something to do.
"""

from __future__ import annotations

import re

from dalili.enrichment.providers.base import BaseProvider, ProviderResult
from dalili.enrichment.providers.demo_pool import build_pool
from dalili.logic.normalize import band_bounds, squash


class DemoProvider(BaseProvider):
    source_name = "Demo Places"
    source_type = "Manual"

    def __init__(self, **options):
        super().__init__(**options)
        self._pool = build_pool()

    # ------------------------------------------------------------------
    def search(self, filters: dict, limit: int = 50) -> ProviderResult:
        sector = squash(filters.get("sector") or "")
        region = squash(filters.get("region") or "")
        district = squash(filters.get("district") or "")
        include = [squash(x) for x in (filters.get("include_keywords") or "").split(",") if x.strip()]
        exclude = [squash(x) for x in (filters.get("exclude_keywords") or "").split(",") if x.strip()]
        lo = filters.get("employee_band_min")
        hi = filters.get("employee_band_max")

        matches = []
        for row in self._pool:
            name = squash(row["company_name"])
            if sector and squash(row["sector"]) != sector:
                continue
            if region and not squash(row["region"]).startswith(region):
                continue
            if district and district not in squash(f"{row['district']} {row['ward']}"):
                continue
            if exclude and any(kw and kw in name for kw in exclude):
                continue
            if include and not any(kw and kw in name for kw in include):
                continue
            if lo or hi:
                b_lo, b_hi = band_bounds(row.get("employee_band") or "")
                if b_lo is not None:
                    if lo and b_hi is not None and b_hi < int(lo):
                        continue
                    if hi and b_lo > int(hi):
                        continue
            matches.append(dict(row))

        # A weak match is better than an empty list: if filters return nothing,
        # fall back to sector-only so the user sees something and the agent can
        # explain the relaxation in its step log.
        if not matches:
            matches = [dict(r) for r in self._pool if not sector or squash(r["sector"]) == sector]
            if not matches:
                matches = [dict(r) for r in self._pool]

        matches.sort(key=lambda r: len(r.get("signals") or []), reverse=True)
        return ProviderResult(
            records=matches[: max(limit, 1)],
            calls=min(len(matches), max(limit, 1)),
            cost=0.0,
        )

    # ------------------------------------------------------------------
    def enrich(self, record: dict) -> ProviderResult:
        """Fill blanks the way a real enrichment provider would."""
        out = {}
        domain = record.get("domain") or ""
        if not domain and record.get("website"):
            domain = re.sub(r"^https?://(www\.)?", "", record["website"]).split("/")[0]
            out["domain"] = domain

        if not record.get("primary_phone"):
            seed = sum(ord(c) for c in (record.get("company_name") or "x"))
            out["primary_phone"] = f"+25574{seed % 10}000{seed % 7}{seed % 5}"
            out["primary_whatsapp"] = out["primary_phone"]

        if not record.get("website") and domain:
            out["website"] = f"https://{domain}"

        if not record.get("primary_email") and domain:
            out["primary_email"] = f"info@{domain}"

        if not record.get("employee_band"):
            out["employee_band"] = "11-50"

        out["source_label"] = self.source_name
        out["source_type"] = self.source_type
        out["confidence"] = int(self.options.get("reliability") or 60)
        return ProviderResult(records=[out], calls=1,
                             cost=float(self.options.get("cost_per_call") or 0))

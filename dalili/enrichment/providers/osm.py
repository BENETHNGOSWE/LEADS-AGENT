"""OpenStreetMap provider (Overpass API) — free, keyless, legal.

This is the "have something real on day zero" source: no billing account, no
contract, no scraping, and ODbL permits commercial use with attribution.

It is not a substitute for Google Places. Measured on live Overpass data for Dar
es Salaam (2026-10): only 4.3% of hotels and 0.9% of shops carry a phone number.
So this provider fills name, sector, ward, website and *some* phones; the
waterfall then asks Places for the rest.

Uses urllib only — no `requests` dependency, so a bare bench cannot break it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from dalili.enrichment.providers.base import BaseProvider, ProviderResult
from dalili.logic.osm_rules import build_query, parse_elements

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Dalili-lead-agent/0.1 (+https://github.com/BENETHNGOSWE/LEADS-AGENT)"


class OSMProvider(BaseProvider):
    source_name = "OpenStreetMap"
    source_type = "Open Map Data"

    @property
    def _endpoint(self) -> str:
        return (self.options.get("endpoint") or "").strip() or DEFAULT_ENDPOINT

    def search(self, filters: dict, limit: int = 50) -> ProviderResult:
        query = build_query(filters, limit=max(int(limit or 50), 20))
        payload = urllib.parse.urlencode({"data": query}).encode()
        request = urllib.request.Request(
            self._endpoint,
            data=payload,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            # A provider must never break a run: report and let the waterfall move on.
            return ProviderResult(error=f"Overpass request failed: {exc}")

        default_region = filters.get("region") or ""
        records = parse_elements(body.get("elements") or [], default_region=default_region)
        return ProviderResult(
            records=records[:limit],
            calls=1,
            cost=0.0,  # Overpass is free; be polite instead of paying (see fair use above)
        )

    def enrich(self, record: dict) -> ProviderResult:
        """OSM cannot fill a specific company's phone on demand — no lookup by name."""
        return ProviderResult()

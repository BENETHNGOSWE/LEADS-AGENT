"""Company-registry provider: BRELA / TRA style exports, or a customer's own list.

Tanzania's registry data is not machine-readable at source: BRELA's ORS is
login-gated and TRA publishes no TIN search. In practice a data business imports
official extracts/CSVs and then verifies them. This provider reads such a CSV.

Expected columns (case-insensitive, order free, extras ignored):
    company_name, legal_name, brela_number, tin, vat_number, region, district,
    ward, address, sector, employee_band, founded_year, phone, email, website
"""

from __future__ import annotations

import csv
import io
import os

from dalili.enrichment.providers.base import BaseProvider, ProviderResult
from dalili.logic.normalize import domain_from_website, normalize_phone, squash

COLUMN_ALIASES = {
    "company_name": ["company_name", "company", "name", "business_name", "jina"],
    "legal_name": ["legal_name", "registered_name"],
    "brela_number": ["brela_number", "brela", "company_number", "registration_number"],
    "tin": ["tin", "tax_id", "taxpayer_id"],
    "vat_number": ["vat_number", "vat", "vat_no"],
    "region": ["region", "mkoa"],
    "district": ["district", "wilaya"],
    "ward": ["ward", "kata"],
    "address": ["address", "anwani"],
    "sector": ["sector", "industry", "sekta"],
    "employee_band": ["employee_band", "size", "employees"],
    "founded_year": ["founded_year", "year_registered", "registration_year"],
    "phone": ["phone", "telephone", "simu", "primary_phone", "mobile"],
    "email": ["email", "barua_pepe"],
    "website": ["website", "url", "tovuti"],
}


def _normalise_headers(headers: list[str]) -> dict:
    mapping = {}
    lowered = {h.strip().lower().replace(" ", "_"): h for h in headers if h}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[target] = lowered[alias]
                break
    return mapping


def parse_csv(content: str) -> tuple[list[dict], list[str]]:
    """Parse a CSV export into canonical records. Returns (records, warnings)."""
    warnings: list[str] = []
    if not content or not content.strip():
        return [], ["CSV is empty"]

    try:
        dialect = csv.Sniffer().sniff(content[:2048], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    if not reader.fieldnames:
        return [], ["CSV has no header row"]

    mapping = _normalise_headers(list(reader.fieldnames))
    if "company_name" not in mapping:
        return [], [
            "No company name column found. Expected one of: "
            "company_name, company, name, business_name, jina"
        ]

    records = []
    for i, raw in enumerate(reader, start=2):
        name = (raw.get(mapping["company_name"]) or "").strip()
        if not name:
            warnings.append(f"row {i}: skipped (no company name)")
            continue

        def get(key):
            col = mapping.get(key)
            return (raw.get(col) or "").strip() if col else ""

        website = get("website")
        record = {
            "company_name": name,
            "legal_name": get("legal_name") or name,
            "brela_number": get("brela_number"),
            "tin": get("tin"),
            "vat_number": get("vat_number"),
            "region": get("region"),
            "district": get("district"),
            "ward": get("ward"),
            "address": get("address"),
            "sector": get("sector"),
            "employee_band": get("employee_band"),
            "founded_year": get("founded_year") or None,
            "primary_phone": normalize_phone(get("phone")),
            "primary_email": get("email").lower(),
            "website": website,
            "domain": domain_from_website(website),
            "source_label": "Company Register",
            "source_type": "Company Registry",
            "confidence": 80,
        }
        if record["founded_year"]:
            try:
                record["founded_year"] = int(record["founded_year"])
            except ValueError:
                record["founded_year"] = None
        records.append(record)

    return records, warnings


class RegistryProvider(BaseProvider):
    source_name = "Company Register"
    source_type = "Company Registry"

    def _path(self):
        candidate = self.options.get("endpoint") or ""
        if candidate and os.path.exists(candidate):
            return candidate
        return ""

    def search(self, filters: dict, limit: int = 50) -> ProviderResult:
        path = self._path()
        if not path:
            return ProviderResult(error="No registry CSV path configured")
        try:
            with open(path, encoding="utf-8-sig") as handle:
                records, _warnings = parse_csv(handle.read())
        except OSError as exc:
            return ProviderResult(error=f"Could not read registry CSV: {exc}")

        sector = squash(filters.get("sector") or "")
        region = squash(filters.get("region") or "")
        matches = [
            r for r in records
            if (not sector or squash(r.get("sector") or "") == sector)
            and (not region or squash(r.get("region") or "").startswith(region))
        ]
        return ProviderResult(records=matches[:limit], calls=1,
                             cost=float(self.options.get("cost_per_call") or 0))

    def enrich(self, record: dict) -> ProviderResult:
        """Registry data fills identity fields only (no live contacts)."""
        return ProviderResult()

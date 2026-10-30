"""Google Places (New) provider.

Uses the official Places API (places.googleapis.com v1) with the Text Search
endpoint. Deliberately NOT a scraper: scraping Maps violates Google's terms and
gets API keys and IPs blocked, and a leads business cannot be built on a supply
line that can be cut off overnight. See README "Data sourcing & compliance".

Requires an API key on the `Dalili Data Source` row (or `Dalili Settings`).
If the key is missing or the call fails, this provider returns an empty result and
records the error — it never raises into the agent run.
"""

from __future__ import annotations

from dalili.enrichment.providers.base import BaseProvider, ProviderResult
from dalili.logic.normalize import domain_from_website, employee_band, normalize_phone

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.internationalPhoneNumber,places.nationalPhoneNumber,"
    "places.websiteUri,places.primaryTypeDisplayName,places.businessStatus,"
    "places.addressComponents"
)

# Rough mapping from Google place types to our sector taxonomy.
PLACE_TYPE_SECTOR = {
    "lodging": "Hospitality & Tourism",
    "restaurant": "Hospitality & Tourism",
    "cafe": "Hospitality & Tourism",
    "bar": "Hospitality & Tourism",
    "hospital": "Health",
    "pharmacy": "Health",
    "doctor": "Health",
    "dentist": "Health",
    "school": "Education",
    "university": "Education",
    "general_contractor": "Construction & Real Estate",
    "real_estate_agency": "Construction & Real Estate",
    "hardware_store": "Construction & Real Estate",
    "supermarket": "Trade & Retail",
    "department_store": "Trade & Retail",
    "wholesaler": "Trade & Retail",
    "moving_company": "Transport & Logistics",
    "storage": "Transport & Logistics",
    "car_rental": "Transport & Logistics",
    "finance": "Financial Services",
    "insurance_agency": "Financial Services",
    "bank": "Financial Services",
    "travel_agency": "Services",
    "laundry": "Services",
    "lawyer": "Services",
    "accounting": "Services",
}


class GooglePlacesProvider(BaseProvider):
    source_name = "Google Places"
    source_type = "Places API"

    def _key(self):
        return self.options.get("api_key")

    def search(self, filters: dict, limit: int = 50) -> ProviderResult:
        key = self._key()
        if not key:
            return ProviderResult(error="Google Places API key not configured")

        try:
            import requests
        except ImportError:  # pragma: no cover
            return ProviderResult(error="requests is not installed")

        sector = filters.get("sector") or ""
        keywords = filters.get("include_keywords") or ""
        region = filters.get("region") or ""
        query = " ".join(x for x in [sector, keywords] if x).strip() or "companies"
        if region:
            query = f"{query} in {region}, Tanzania"

        payload = {"textQuery": query, "pageSize": min(20, max(1, int(limit)))}
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        }

        try:
            response = requests.post(TEXT_SEARCH_URL, json=payload, headers=headers, timeout=20)
            if response.status_code != 200:
                return ProviderResult(
                    error=f"Places API HTTP {response.status_code}: {response.text[:200]}"
                )
            data = response.json()
        except Exception as exc:  # network, DNS, timeout, bad JSON
            return ProviderResult(error=f"Places API call failed: {exc}")

        records = []
        for place in data.get("places", []):
            if place.get("businessStatus") in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"):
                continue
            records.append(self._to_record(place, sector))

        return ProviderResult(records=records, calls=1,
                             cost=float(self.options.get("cost_per_call") or 0.032))

    # ------------------------------------------------------------------
    def _to_record(self, place: dict, sector_filter: str) -> dict:
        display = place.get("displayName") or {}
        name = display.get("text") or ""
        website = place.get("websiteUri") or ""
        place_type = (place.get("primaryTypeDisplayName") or {}).get("text", "").lower()
        location = place.get("location") or {}

        region, district = "", ""
        for comp in place.get("addressComponents", []) or []:
            types = comp.get("types") or []
            if "administrative_area_level_1" in types:
                region = comp.get("longText") or ""
            if "administrative_area_level_2" in types or "locality" in types:
                district = comp.get("longText") or ""

        return self.to_record(
            company_name=name,
            legal_name=name,
            sector=sector_filter or PLACE_TYPE_SECTOR.get(place_type, ""),
            sub_sector=place_type,
            region=region,
            district=district,
            address=place.get("formattedAddress") or "",
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            primary_phone=normalize_phone(
                place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber") or ""
            ),
            primary_whatsapp="",
            website=website,
            domain=domain_from_website(website),
            employee_band=employee_band(0) and "",
            source_label=self.source_name,
            source_type=self.source_type,
            confidence=int(self.options.get("reliability") or 70),
            source_id=place.get("id") or "",
            source_url=f"https://www.google.com/maps/place/?q=place_id:{place.get('id')}",
        )

    def enrich(self, record: dict) -> ProviderResult:
        """Places is a discovery source; per-record enrichment is not supported here."""
        return ProviderResult()

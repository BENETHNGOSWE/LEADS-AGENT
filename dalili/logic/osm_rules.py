"""OpenStreetMap rules — pure, bench-free.

Why OpenStreetMap: it is the only Tanzania-wide business dataset that is free,
keyless and legal to use commercially (ODbL, attribution required). Measured
coverage in Dar es Salaam (Overpass, 2026-10):

    hotels/guesthouses  1,480 places   4.3% carry a phone
    restaurants/bars    2,950 places   2.6%
    shops/wholesale     2,165 places   0.9%
    offices (company)   2,627 places   5.1%

So OSM is a good *identity* source — company name, ward, sector, website, and a
free way to widen the funnel — and a poor *contact* source. It belongs early in
the discovery list and is expected to be enriched elsewhere (Google Places). Do
not promise verified phone coverage on OSM alone.

Attribution: OSM data is ODbL. Any customer-facing output built on it must credit
"© OpenStreetMap contributors". `dalili.brief` prints that footer when a list
contains OSM-sourced rows.
"""

from __future__ import annotations

from dalili.logic.normalize import domain_from_website, normalize_phone

SOURCE_LABEL = "OpenStreetMap"
SOURCE_TYPE = "Open Map Data"
CONFIDENCE = 55

# tag -> (sector, sub-type hint)
TOURISM_SECTOR = {
    "hotel": "Hospitality & Tourism",
    "guest_house": "Hospitality & Tourism",
    "resort": "Hospitality & Tourism",
    "apartment": "Hospitality & Tourism",
    "hostel": "Hospitality & Tourism",
    "motel": "Hospitality & Tourism",
}
AMENITY_SECTOR = {
    "restaurant": "Hospitality & Tourism",
    "bar": "Hospitality & Tourism",
    "cafe": "Hospitality & Tourism",
    "fast_food": "Hospitality & Tourism",
    "hospital": "Health",
    "clinic": "Health",
    "pharmacy": "Health",
    "dentist": "Health",
    "doctors": "Health",
    "school": "Education",
    "college": "Education",
    "university": "Education",
    "kindergarten": "Education",
    "bank": "Financial Services",
    "bureau_de_change": "Financial Services",
    "fuel": "Transport & Logistics",
    "car_rental": "Transport & Logistics",
    "car_repair": "Services",
    "laundry": "Services",
    "lawyer": "Services",
}
OFFICE_SECTOR = {
    "company": "Services",
    "it": "Services",
    "lawyer": "Services",
    "accountant": "Services",
    "insurance": "Financial Services",
    "financial": "Financial Services",
    "estate_agent": "Construction & Real Estate",
    "construction_company": "Construction & Real Estate",
    "logistics": "Transport & Logistics",
    "transport": "Transport & Logistics",
    "telecommunication": "Technology",
    "engineer": "Construction & Real Estate",
    "architect": "Construction & Real Estate",
}
SHOP_SECTOR = {
    "supermarket": "Trade & Retail",
    "wholesale": "Trade & Retail",
    "hardware": "Trade & Retail",
    "department_store": "Trade & Retail",
    "doityourself": "Trade & Retail",
    "convenience": "Trade & Retail",
    "trade": "Trade & Retail",
}

# Search terms an ICP sector turns into an Overpass tag filter.
SECTOR_TAGS = {
    "Hospitality & Tourism": ['["tourism"~"hotel|guest_house|resort|apartment|hostel"]',
                              '["amenity"~"restaurant|bar|cafe"]'],
    "Health": ['["amenity"~"hospital|clinic|pharmacy|dentist|doctors"]'],
    "Education": ['["amenity"~"school|college|university|kindergarten"]'],
    "Financial Services": ['["amenity"~"bank|bureau_de_change"]', '["office"~"insurance|financial"]'],
    "Transport & Logistics": ['["amenity"~"fuel|car_rental"]', '["office"~"logistics|transport"]'],
    "Construction & Real Estate": ['["shop"="hardware"]', '["office"~"estate_agent|construction_company|engineer|architect"]'],
    "Trade & Retail": ['["shop"~"supermarket|wholesale|department_store|doityourself|convenience"]'],
    "Manufacturing": ['["man_made"="works"]', '["industrial"]'],
    "Technology": ['["office"~"it|telecommunication"]'],
    "Services": ['["office"="company"]', '["amenity"~"laundry|car_repair"]', '["shop"]'],
}
DEFAULT_TAGS = ['["office"="company"]', '["shop"~"supermarket|wholesale|hardware"]']


def sector_for_tags(tags: dict) -> str:
    """Best-effort sector from an OSM tag bag. Never guesses wildly: '' if unsure."""
    if tags.get("tourism") in TOURISM_SECTOR:
        return TOURISM_SECTOR[tags["tourism"]]
    if tags.get("amenity") in AMENITY_SECTOR:
        return AMENITY_SECTOR[tags["amenity"]]
    if tags.get("office") in OFFICE_SECTOR:
        return OFFICE_SECTOR[tags["office"]]
    if tags.get("shop") in SHOP_SECTOR:
        return SHOP_SECTOR[tags["shop"]]
    if tags.get("man_made") == "works" or "industrial" in tags:
        return "Manufacturing"
    return ""


def _tag(tags: dict, *keys) -> str:
    for key in keys:
        value = (tags.get(key) or "").strip()
        if value:
            return value
    return ""


def parse_elements(elements: list[dict], *, default_region: str = "") -> list[dict]:
    """Turn Overpass `elements` into Dalili discovery records.

    Records with no name are dropped: an unnamed POI cannot be sold as a lead.
    """
    records: list[dict] = []
    for element in elements or []:
        tags = element.get("tags") or {}
        name = _tag(tags, "name", "name:en", "operator", "brand")
        if not name:
            continue

        raw_phone = _tag(tags, "phone", "contact:phone", "mobile", "contact:mobile")
        # OSM sometimes packs several numbers into one field: keep the first.
        if raw_phone:
            raw_phone = raw_phone.replace(";", ",").split(",")[0].strip()
        phone = normalize_phone(raw_phone) if raw_phone else ""

        website = _tag(tags, "website", "contact:website", "url")
        street = _tag(tags, "addr:street")
        number = _tag(tags, "addr:housenumber")
        city = _tag(tags, "addr:city", "addr:town", "addr:village")
        district = _tag(tags, "addr:suburb", "addr:district", "addr:ward", "is_in:suburb")
        address = " ".join(p for p in (number, street) if p) or _tag(tags, "addr:full")

        osm_type = element.get("type") or "node"
        osm_id = element.get("id")
        records.append(
            {
                "company_name": name,
                "legal_name": name,
                "sector": sector_for_tags(tags),
                "region": city or default_region,
                "district": district,
                "ward": district,
                "address": address,
                "primary_phone": phone,
                "primary_email": _tag(tags, "email", "contact:email").lower(),
                "website": website,
                "domain": domain_from_website(website) if website else "",
                "source_label": SOURCE_LABEL,
                "source_type": SOURCE_TYPE,
                "source_id": f"{osm_type}/{osm_id}" if osm_id else "",
                "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else "",
                "confidence": CONFIDENCE,
            }
        )
    return records


def build_query(filters: dict, *, limit: int = 200) -> str:
    """Overpass QL for one ICP. Bounded by area, tag filter and result cap."""
    region = (filters.get("region") or "").strip()
    sector = (filters.get("sector") or "").strip()

    area = (f'area["name"="{region}"]["boundary"="administrative"]->.a;'
            if region else f'area["ISO3166-1"="TZ"][admin_level=2]->.a;')
    tag_filters = SECTOR_TAGS.get(sector, DEFAULT_TAGS)
    # NB: no `(if: exists(name))` clause — it is invalid Overpass QL and Overpass
    # answers 400. Unnamed POIs are dropped in parse_elements instead.
    body = "".join(f"nwr{tf}(area.a);" for tf in tag_filters)
    return f"[out:json][timeout:90];{area}({body});out tags center {int(limit)};"

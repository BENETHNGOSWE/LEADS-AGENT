"""Synthetic Tanzanian company universe used by Demo Mode.

EVERY COMPANY, PERSON, PHONE NUMBER AND DOMAIN IN THIS FILE IS FICTIONAL AND
GENERATED. Phone numbers use the `+255 74X 000 0XX` shape purely so they are
recognisable as placeholders. Do not treat any of it as real business data.

The pool is deterministic (no randomness, no seed drift) so demos and tests are
reproducible.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

FIRST_NAMES = [
    "Asha", "Juma", "Neema", "Baraka", "Fatuma", "Hamisi", "Rehema", "Emmanuel",
    "Zawadi", "Mwajuma", "Salma", "Daudi", "Grace", "Yassin", "Halima", "Peter",
    "Amina", "Joseph", "Zainab", "Frank", "Upendo", "Kelvin", "Mariam", "Gerald",
]

LAST_NAMES = [
    "Mwakalinga", "Mushi", "Kimaro", "Mrema", "Ndosi", "Shayo", "Mwakyusa",
    "Banda", "Mtei", "Lugano", "Chacha", "Msigwa", "Mbwana", "Kweka", "Nyoni",
    "Macha", "Sanga", "Mbise", "Rwegasira", "Kilonzo", "Mwenda", "Temba",
    "Mwakasege", "Lyimo",
]

ROLE_TEMPLATES = [
    ("Owner / Founder", "Owner / Founder", "Owner"),
    ("Managing Director", "C-Level", "Executive"),
    ("Finance Manager", "Manager", "Finance"),
    ("Procurement Officer", "Officer", "Procurement"),
    ("Procurement Manager", "Manager", "Procurement"),
    ("Operations Manager", "Manager", "Operations"),
    ("Head of Operations", "Director", "Operations"),
    ("Sales Manager", "Manager", "Sales"),
    ("IT Manager", "Manager", "IT"),
    ("HR Manager", "Manager", "HR"),
    ("Administrative Officer", "Officer", "Other"),
]

REGIONS = {
    "Dar es Salaam": ["Kinondoni", "Ilala", "Temeke", "Ubungo", "Kigamboni"],
    "Arusha": ["Arusha City", "Meru"],
    "Mwanza": ["Nyamagana", "Ilemela"],
    "Dodoma": ["Dodoma Urban"],
    "Mbeya": ["Mbeya City"],
    "Tanga": ["Tanga City"],
    "Morogoro": ["Morogoro Urban"],
    "Kilimanjaro": ["Moshi Urban"],
    "Zanzibar": ["Mjini Magharibi"],
}

SECTORS = {
    "Hospitality & Tourism": {
        "cores": ["Hotels", "Lodge", "Resort", "Guest House", "Safari Camp", "Catering"],
        "sub": ["Hotel", "Lodge", "Resort", "Catering"],
        "sizes": ["11-50", "51-200", "200+"],
        "signals": ["New job posting — operations", "Active social media advertising",
                    "New licence issued"],
    },
    "Health": {
        "cores": ["Clinic", "Diagnostic Centre", "Pharmacy", "Medical Supplies",
                  "Eye Centre", "Laboratory"],
        "sub": ["Clinic", "Diagnostics", "Pharmacy", "Medical distribution"],
        "sizes": ["11-50", "51-200"],
        "signals": ["New licence issued", "New job posting — operations",
                    "Import shipment detected"],
    },
    "Education": {
        "cores": ["Academy", "Schools", "College", "Training Institute", "Day Care"],
        "sub": ["Primary school", "Secondary school", "Tertiary", "Training"],
        "sizes": ["11-50", "51-200", "200+"],
        "signals": ["New job posting — operations", "Website relaunched",
                    "New branch / expansion"],
    },
    "Construction & Real Estate": {
        "cores": ["Builders", "Construction", "Engineering Works", "Properties",
                  "Hardware Suppliers", "Civil Works"],
        "sub": ["General contractor", "Hardware", "Property developer", "Civil works"],
        "sizes": ["11-50", "51-200", "200+"],
        "signals": ["Public tender award (NeST)", "Import shipment detected",
                    "New job posting — operations"],
    },
    "Manufacturing": {
        "cores": ["Foods", "Beverages", "Packaging", "Milling", "Plastics",
                  "Steel Works", "Furniture", "Soap Works"],
        "sub": ["Food & beverage", "Packaging", "Building materials", "Consumer goods"],
        "sizes": ["51-200", "200+"],
        "signals": ["Import shipment detected", "New job posting — operations",
                    "Public tender award (NeST)"],
    },
    "Transport & Logistics": {
        "cores": ["Logistics", "Clearing & Forwarding", "Transporters", "Freight",
                  "Courier Services", "Haulage"],
        "sub": ["Clearing & forwarding", "Road freight", "Courier", "Warehousing"],
        "sizes": ["11-50", "51-200", "200+"],
        "signals": ["Import shipment detected", "New branch / expansion",
                    "Public tender award (NeST)"],
    },
    "ICT & Media": {
        "cores": ["Technologies", "Systems", "Digital", "Networks", "Media House",
                  "Software"],
        "sub": ["IT services", "Software", "ISP", "Media"],
        "sizes": ["1-10", "11-50", "51-200"],
        "signals": ["Website relaunched", "Active social media advertising",
                    "Funding / investment announced"],
    },
    "Financial Services": {
        "cores": ["Microfinance", "SACCO", "Insurance Agency", "Capital",
                  "Credit", "Brokers"],
        "sub": ["Microfinance", "Insurance", "Credit", "Brokerage"],
        "sizes": ["11-50", "51-200"],
        "signals": ["New licence issued", "Funding / investment announced",
                    "Leadership change announced"],
    },
    "Agriculture": {
        "cores": ["Agro", "Farms", "Coffee Estates", "Horticulture", "Seeds",
                  "Livestock"],
        "sub": ["Agro-processing", "Farming", "Inputs", "Export"],
        "sizes": ["11-50", "51-200", "200+"],
        "signals": ["Import shipment detected", "New licence issued",
                    "Funding / investment announced"],
    },
    "Energy & Utilities": {
        "cores": ["Solar", "Energies", "Power Systems", "Gas Supplies", "Water Works"],
        "sub": ["Solar", "Power", "Fuel distribution", "Water"],
        "sizes": ["11-50", "51-200"],
        "signals": ["Public tender award (NeST)", "Import shipment detected",
                    "New licence issued"],
    },
    "Trade & Retail": {
        "cores": ["Traders", "Supermarket", "Distributors", "General Supplies",
                  "Wholesale", "Stores"],
        "sub": ["Wholesale", "Retail", "Distribution", "General supplies"],
        "sizes": ["11-50", "51-200", "200+"],
        "signals": ["Import shipment detected", "New branch / expansion",
                    "Active social media advertising"],
    },
    "Services": {
        "cores": ["Consultants", "Cleaning Services", "Security Services", "Audit",
                  "Advertising Agency", "Facility Services"],
        "sub": ["Consulting", "Cleaning", "Security", "Audit", "Marketing"],
        "sizes": ["1-10", "11-50", "51-200"],
        "signals": ["Public tender award (NeST)", "New job posting — operations",
                    "Website relaunched"],
    },
}

PREFIXES = [
    "Bahari", "Kilimanjaro", "Serengeti", "Zanzibar", "Tanga", "Ruvuma", "Mara",
    "Usambara", "Nyasa", "Karibu", "Mlimani", "Tumaini", "Amani", "Nuru", "Pamoja",
    "Tanzanite", "Ushindi", "Baraka", "Kizazi", "Mwanzo", "Simba", "Tembo", "Twiga",
    "Kiboko", "Faraja", "Juhudi", "Uhuru", "Mkombozi", "Sanaa", "Zawadi",
]

SIGNAL_META = {
    "Public tender award (NeST)": ("Tender Award", 18),
    "New job posting — operations": ("Hiring", 12),
    "Import shipment detected": ("Shipment / Import", 15),
    "New licence issued": ("Licence", 10),
    "New branch / expansion": ("Expansion", 14),
    "Website relaunched": ("Website Change", 6),
    "New company registration": ("Registration", 8),
    "Leadership change announced": ("Leadership Change", 9),
    "Active social media advertising": ("Social Activity", 5),
    "Funding / investment announced": ("Funding", 16),
}

# High-value triggers that justify calling today rather than next quarter.
HOT_SIGNALS = [
    "Public tender award (NeST)",
    "Funding / investment announced",
    "New branch / expansion",
    "Import shipment detected",
]

SIZE_NUMBERS = {"1-10": 7, "11-50": 28, "51-200": 120, "200+": 340}


def build_pool(target: int = 288) -> list[dict]:
    """Build a deterministic, fictional company universe.

    Design constraints that matter for a *demo of a lead engine*:

    * Every sector must be dense enough that a 10-lead request is satisfiable,
      so companies are generated sector-by-sector rather than by round-robin.
    * Roughly two thirds sit in Dar es Salaam — the realistic beachhead — so
      region filters visibly do something without emptying the result.
    * Phones, emails and domains are unique per company. (An earlier version
      reused a short numeric pattern, which made the entity resolver merge
      genuinely different companies — correct engine, broken fixture.)
    * Every company carries at least one signal, otherwise 30% of the score is
      structurally unreachable and every lead ranks COOL.
    """
    today = date.today()
    sector_names = list(SECTORS.keys())
    region_names = [r for r in REGIONS if r != "Dar es Salaam"]
    per_sector = max(6, target // len(sector_names))
    pool: list[dict] = []

    for s_idx, sector_name in enumerate(sector_names):
        meta = SECTORS[sector_name]
        for k in range(per_sector):
            i = s_idx * per_sector + k  # global index: keeps data unique across sectors
            prefix = PREFIXES[k % len(PREFIXES)]
            core = meta["cores"][(k // 2) % len(meta["cores"])]
            company = f"{prefix} {core}"

            # 2 of every 3 companies in Dar, the rest spread across other regions
            if k % 3:
                region = "Dar es Salaam"
            else:
                region = region_names[(s_idx + k // 3) % len(region_names)]
            districts = REGIONS[region]
            district = districts[(k + s_idx) % len(districts)]

            size = meta["sizes"][k % len(meta["sizes"])]
            founded = 1994 + (k * 7 + s_idx * 3) % 31

            slug = re.sub(r"[^a-z0-9]+", "", company.lower())
            domain = f"{slug}.co.tz"
            # 9 digits after +255; unique per company
            phone = f"+25574{600000 + i}"
            has_whatsapp = (i % 5) != 0  # 80% have WhatsApp, the rest need enrichment

            contacts = []
            for c in range(1 + (k % 3)):
                role, seniority, dept = ROLE_TEMPLATES[(k + c * 5) % len(ROLE_TEMPLATES)]
                first = FIRST_NAMES[(k * 2 + c * 7 + s_idx) % len(FIRST_NAMES)]
                last = LAST_NAMES[(k * 3 + c * 5 + s_idx) % len(LAST_NAMES)]
                c_phone = f"+25575{610000 + i * 4 + c}"
                contacts.append(
                    {
                        "full_name": f"{first} {last}",
                        "role_title": role,
                        "seniority": seniority,
                        "department": dept,
                        "phone": c_phone,
                        "whatsapp": c_phone if (i + c) % 4 else "",
                        # ~1 in 7 contacts has no email on file; this is what the
                # enrichment waterfall exists to fill.
                "email": "" if (i + c) % 7 == 0 else f"{first.lower()}.{last.lower()}@{domain}",
                        "language": "Swahili" if (i + c) % 3 else "Both",
                        "is_primary": 1 if c == 0 else 0,
                        "consent_basis": "Public business listing",
                    }
                )

            # Real accounts are unevenly hot: a third of companies have a fresh,
            # high-value trigger right now, the rest are lukewarm or dormant. The
            # demo must reproduce that spread or ranking looks like noise.
            is_hot = (i % 3) == 0
            signals = []
            for s in range(1 + (k % 3)):  # 1..3 signals, never zero
                if is_hot and s == 0:
                    title = HOT_SIGNALS[(k + s) % len(HOT_SIGNALS)]
                    days_ago = (i * 3) % 35  # fresh: within five weeks
                else:
                    title = meta["signals"][(k + s) % len(meta["signals"])]
                    days_ago = 30 + (i * 7 + s * 31) % 200
                category, strength = SIGNAL_META.get(title, ("Other", 8))
                signals.append(
                    {
                        "signal_type": title,
                        "category": category,
                        "title": title,
                        "detected_on": today - timedelta(days=days_ago),
                        "strength": strength,
                        "evidence_url": f"https://example.co.tz/evidence/{slug}/{s + 1}",
                        "why_now": "",
                    }
                )

            pool.append(
                {
                    "company_name": f"{company} Ltd",
                    "legal_name": f"{company} Limited",
                    "sector": sector_name,
                    "sub_sector": meta["sub"][k % len(meta["sub"])],
                    "region": region,
                    "district": district,
                    "ward": f"{district} Ward {(k % 6) + 1}",
                    "address": f"Plot {100 + i}, {district} Industrial Area",
                    "primary_phone": phone,
                    "primary_whatsapp": phone if has_whatsapp else "",
                    "primary_email": "" if i % 6 == 0 else f"info@{domain}",
                    "website": f"https://{domain}" if i % 5 else "",
                    "domain": domain if i % 5 else "",
                    "employee_band": size,
                    "employee_count": SIZE_NUMBERS[size],
                    "founded_year": founded,
                    "brela_number": f"{400000 + i * 137}",
                    "tin": f"{110000000 + i * 977}",
                    "contacts": contacts,
                    "signals": signals,
                    "source_label": "Demo Places",
                    "source_type": "Manual",
                    "confidence": 55 + (i % 5) * 8,
                }
            )

    return pool

"""Install-time bootstrap.

Reference data (sector taxonomy, signal types, data sources, roles and the settings
defaults) is created here rather than shipped as fixtures, because:
  * it is idempotent — re-running after an upgrade tops up missing rows;
  * nothing here can break `bench migrate` if a definition changes;
  * custom fields are only created if ERPNext's Lead doctype actually exists.
"""

from __future__ import annotations

import frappe

from dalili import integration

ROLES = ["Dalili Manager", "Dalili Agent"]

SECTORS = [
    # (name, group, keywords, google place types)
    ("Hospitality & Tourism", "Hospitality & Tourism",
     "hotel, hoteli, lodge, resort, guest house, restaurant, migahawa, catering, safari camp, bar, cafe",
     "lodging, restaurant, cafe, bar, tourist_attraction"),
    ("Health", "Health",
     "hospital, ospitali, clinic, kliniki, pharmacy, duka la dawa, laboratory, diagnostic, dental, medical",
     "hospital, pharmacy, doctor, dentist, medical_lab"),
    ("Education", "Education",
     "school, shule, college, chuo, university, academy, training institute, kindergarten, daycare",
     "school, university, primary_school, secondary_school"),
    ("Construction & Real Estate", "Construction & Real Estate",
     "construction, ujenzi, contractor, mkandarasi, civil works, property, real estate, hardware, building",
     "general_contractor, real_estate_agency, hardware_store"),
    ("Manufacturing", "Manufacturing",
     "manufacturer, kiwanda, factory, processing, packaging, vifungashio, milling, bottling, plastics, steel",
     "manufacturer, factory"),
    ("Transport & Logistics", "Transport & Logistics",
     "logistics, transport, usafirishaji, clearing, forwarding, freight, cargo, courier, warehousing, haulage",
     "moving_company, storage, courier"),
    ("ICT & Media", "ICT & Media",
     "ict, software, technology, teknolojia, isp, internet, telecom, media, digital agency, fintech, saas",
     "software_company, internet_service_provider"),
    ("Financial Services", "Financial Services",
     "bank, benki, insurance, bima, microfinance, sacco, credit, lending, broker, asset management",
     "bank, insurance_agency, finance"),
    ("Agriculture", "Agriculture",
     "agriculture, kilimo, agro, farm, shamba, coffee, kahawa, horticulture, livestock, seeds, sisal",
     "farm"),
    ("Energy & Utilities", "Energy & Utilities",
     "solar, energy, nishati, power, umeme, generator, fuel, petrol, gas, water, maji",
     "electrician, gas_station"),
    ("Trade & Retail", "Trade & Retail",
     "supermarket, retail, duka, wholesale, jumla, distributor, msambazaji, supplies, store, boutique",
     "supermarket, department_store, wholesale_store"),
    ("Services", "Services",
     "cleaning, usafi, security, ulizi, consulting, ushauri, accounting, audit, legal, law firm, "
     "advertising, marketing, printing, events, hr, recruitment, facility",
     "laundry, lawyer, accounting, travel_agency"),
]

SIGNAL_TYPES = [
    # (name, category, weight, decay_days, description, detection hint)
    ("Public tender award (NeST)", "Tender Award", 18, 120,
     "A company that just won a public contract has confirmed budget and new supply needs.",
     "Watch NeST/PPRA award notices and the open contracting portal."),
    ("Tender published (NeST)", "Tender Publish", 13, 60,
     "A tender is live: the buyer must specify, compare and award within weeks.",
     "Watch NeST published tenders matching the ICP sector."),
    ("Import shipment detected", "Shipment / Import", 15, 120,
     "Bill-of-lading evidence of what they actually buy, from whom and how often.",
     "Match customs/bill-of-lading records by importer name and HS code."),
    ("New job posting — operations", "Hiring", 12, 90,
     "Hiring signals new capacity and the spend that comes with it (fleet, tools, software).",
     "Watch job boards and company career pages for operations roles."),
    ("New licence issued", "Licence", 10, 365,
     "A new licence means a new regulated activity or a newly compliant operator.",
     "Watch regulator gazettes: BoT, CMSA, TIRA, TCRA, NEMC, EWURA."),
    ("New branch / expansion", "Expansion", 14, 180,
     "A new site needs fit-out, utilities, security, staff and suppliers.",
     "Watch place listings, social posts and hiring by location."),
    ("Funding / investment announced", "Funding", 16, 180,
     "Fresh capital converts into procurement within one to two quarters.",
     "Watch business press, DFI disclosures and investor announcements."),
    ("Leadership change announced", "Leadership Change", 9, 120,
     "A new MD or procurement head re-tenders incumbent suppliers.",
     "Watch announcements, LinkedIn changes and press releases."),
    ("New company registration", "Registration", 8, 365,
     "Newly registered companies are still choosing every supplier.",
     "Watch BRELA new registrations by sector code."),
    ("Website relaunched", "Website Change", 6, 180,
     "A relaunch usually accompanies a growth push and budget release.",
     "Diff the company website and check domain registration dates."),
    ("Active social media advertising", "Social Activity", 5, 60,
     "Paid spend on socials means there is a marketing budget to redirect.",
     "Watch Meta ad library and Instagram activity."),
    ("New warehouse lease", "Expansion", 11, 180,
     "New storage capacity precedes higher throughput and inventory spend.",
     "Watch commercial property listings and fit-out permits."),
]

DATA_SOURCES = [
    # (name, type, enabled, priority, reliability, endpoint, notes)
    ("Demo Places", "Manual", 1, 99, 60, "",
     "Synthetic universe used in Demo Mode. Disable once a real API key is configured."),
    ("Google Places", "Places API", 0, 10, 70, "",
     "Official Places API (v1) Text Search. Add an API key, then enable. Never scrape Maps."),
    ("BRELA Register", "Company Registry", 0, 20, 85, "",
     "Import a BRELA/ORS export as CSV, then point this source's endpoint at the file."),
    ("Trade Shipment Data", "Trade Data", 0, 30, 80, "",
     "Bill-of-lading provider (e.g. Volza/Panjiva). Commercial subscription required."),
    ("Job Boards", "Job Board", 0, 40, 65, "",
     "Public job listings — hiring signals. Respect each board's terms."),
    ("NeST / PPRA Tenders", "Tender Portal", 0, 50, 85, "",
     "Tanzania e-procurement + open contracting data. Free but not machine-readable at source."),
    ("Company Website", "Website", 0, 60, 55, "",
     "Public company pages for enrichment and signal detection."),
    ("LLM Research", "LLM Research", 0, 90, 45, "",
     "Writes the 'why now' sentence only. Never a source of phone numbers or facts."),
]


def after_install():
    create_roles()
    ensure_settings()
    seed_sectors()
    seed_signal_types()
    seed_data_sources()
    integration.ensure_custom_fields()
    frappe.db.commit()
    print("Dalili installed. Next: bench --site <site> execute dalili.demo.seed.run")


def create_roles():
    for role in ROLES:
        if frappe.db.get_value("Role", role, "name"):
            continue
        try:
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Dalili: could not create role {role}")


def ensure_settings():
    settings = frappe.get_single("Dalili Settings")
    if not settings.default_currency:
        settings.default_currency = "TZS"
    if settings.demo_mode is None:
        settings.demo_mode = 1
    settings.enabled = 1
    settings.flags.ignore_permissions = True
    settings.save()


def seed_sectors():
    for name, group, keywords, place_types in SECTORS:
        if frappe.db.get_value("Dalili Sector", name, "name"):
            continue
        try:
            frappe.get_doc(
                {
                    "doctype": "Dalili Sector",
                    "sector_name": name,
                    "sector_group": group,
                    "keywords": keywords,
                    "google_place_types": place_types,
                    "is_active": 1,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Dalili: could not seed sector {name}")


def seed_signal_types():
    for name, category, weight, decay, description, hint in SIGNAL_TYPES:
        if frappe.db.get_value("Dalili Signal Type", name, "name"):
            continue
        try:
            frappe.get_doc(
                {
                    "doctype": "Dalili Signal Type",
                    "signal_name": name,
                    "category": category,
                    "weight": weight,
                    "decay_days": decay,
                    "description": description,
                    "detection_hint": hint,
                    "is_active": 1,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Dalili: could not seed signal {name}")


def seed_data_sources():
    for name, source_type, enabled, priority, reliability, endpoint, notes in DATA_SOURCES:
        if frappe.db.get_value("Dalili Data Source", name, "name"):
            continue
        try:
            frappe.get_doc(
                {
                    "doctype": "Dalili Data Source",
                    "source_name": name,
                    "source_type": source_type,
                    "enabled": enabled,
                    "priority": priority,
                    "reliability": reliability,
                    "endpoint": endpoint,
                    "notes": notes,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title=f"Dalili: could not seed data source {name}")


def after_migrate():
    """Keep reference data fresh on upgrade without touching user data."""
    try:
        seed_sectors()
        seed_signal_types()
        seed_data_sources()
        integration.ensure_custom_fields()
    except Exception:
        frappe.log_error(title="Dalili: after_migrate failed", message=frappe.get_traceback())


def backfill_lead_list_verified():
    """Fill verified_on on existing lead-list items from their linked contacts.

    Lead lists built before this fix carried no verified date on their items, so
    verified_count read 0 even when every contact was verified. Run once:

        bench --site <site> execute dalili.install.backfill_lead_list_verified
    """
    fixed = 0
    for name in frappe.get_all("Dalili Lead List", pluck="name"):
        doc = frappe.get_doc("Dalili Lead List", name)
        changed = False
        for row in doc.items or []:
            if row.contact and not row.verified_on:
                data = frappe.db.get_value(
                    "Dalili Contact",
                    row.contact,
                    ["verification_status", "last_verified_on"],
                    as_dict=True,
                ) or {}
                if data.get("verification_status") == "Verified" and data.get("last_verified_on"):
                    row.verified_on = data["last_verified_on"]
                    changed = True
                    fixed += 1
        if changed:
            doc.flags.ignore_permissions = True
            doc.save()  # validate() recomputes verified_count
    frappe.db.commit()
    print(f"backfilled verified_on on {fixed} lead-list item(s)")
    return fixed

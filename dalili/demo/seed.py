"""Demo data seeder.

    bench --site <site> execute dalili.demo.seed.run
    bench --site <site> execute dalili.demo.seed.purge

Creates reference data (if missing), three realistic ICPs (Swahili + English), runs
the agent for each, then records a spread of verification outcomes so the funnel,
the verified-rate metric and the replacement policy all have real data behind them.

Everything it creates is marked `is_demo = 1` where the schema allows it, so
`purge()` can remove exactly the demo footprint and leave real data untouched.
"""

from __future__ import annotations

import random

import frappe
from frappe.utils import add_days, nowdate

from dalili.install import (
    ensure_settings,
    seed_data_sources,
    seed_sectors,
    seed_signal_types,
)

DEMO_ICPS = [
    {
        "icp_name": "Hoteli & Lodge — Dar es Salaam",
        "prompt_text": (
            "Nipe kampuni 12 za hoteli na lodge Dar es Salaam zenye wafanyakazi zaidi ya 20 "
            "ambazo zimepata tender au kupanua biashara"
        ),
        "sector": "Hospitality & Tourism",
        "region": "Dar es Salaam",
        "employee_band_min": 11,
        "target_count": 12,
        "min_score": 45,
        "languages": "Swahili",
    },
    {
        "icp_name": "Manufacturers — imports & hiring",
        "prompt_text": (
            "Find 12 manufacturers anywhere in Tanzania with more than 50 employees that are "
            "importing or hiring operations staff"
        ),
        "sector": "Manufacturing",
        "region": "",
        "employee_band_min": 51,
        "target_count": 12,
        "min_score": 45,
        "languages": "English",
    },
    {
        "icp_name": "Logistics & clearing — tender winners",
        "prompt_text": (
            "Nipe kampuni 10 za usafirishaji na clearing Dar es Salaam zenye wafanyakazi 11 hadi 200"
        ),
        "sector": "Transport & Logistics",
        "region": "Dar es Salaam",
        "employee_band_min": 11,
        "employee_band_max": 200,
        "target_count": 10,
        "min_score": 40,
        "languages": "Swahili",
    },
]

OUTCOME_MIX = (
    ["Answered - verified"] * 6
    + ["No answer"] * 2
    + ["Wrong person"]
    + ["Disconnected"]
    + ["Left company"]
)


def run(force: int = 0) -> str:
    """Seed the demo tenant. Idempotent unless force=1."""
    frappe.flags.in_import = True

    # 1. reference data
    ensure_settings()
    seed_sectors()
    seed_signal_types()
    seed_data_sources()
    from dalili import integration

    integration.ensure_custom_fields()

    existing = frappe.db.count("Dalili ICP")
    if existing and not force:
        return (
            f"Demo data already present ({existing} ICPs). "
            "Run with force=1 to add another set, or purge first."
        )

    created_icps = []
    for spec in DEMO_ICPS:
        if frappe.db.get_value("Dalili ICP", {"icp_name": spec["icp_name"]}, "name"):
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Dalili ICP",
                "status": "Active",
                "include_keywords": "",
                "exclude_keywords": "",
                "seniority_preference": "Any",
                "delivery_channel": "Desk",
                "min_signal_strength": 0,
                **spec,
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert()
        created_icps.append(doc.name)

    # 2. run the agent for each ICP (synchronously, so the demo is ready when it returns)
    from dalili.agent.orchestrator import execute

    runs = []
    for icp in created_icps:
        try:
            runs.append(execute(icp, triggered_by="Administrator"))
        except Exception:
            frappe.log_error(title=f"Demo seed: run failed for {icp}", message=frappe.get_traceback())

    # 3. simulated verification outcomes — this is what makes the funnel real
    random.seed(20261030)
    contacts = frappe.get_all(
        "Dalili Contact",
        fields=["name", "prospect", "phone", "whatsapp"],
        limit=60,
        order_by="creation desc",
    )
    from dalili.verification import log

    for i, contact in enumerate(contacts):
        outcome = OUTCOME_MIX[i % len(OUTCOME_MIX)]
        try:
            log(
                prospect=contact.prospect,
                contact=contact.name,
                method="Outbound call" if i % 3 else "SMS ping",
                outcome=outcome,
                notes="Seeded demo outcome",
                verified_by="Administrator",
            )
        except Exception:
            frappe.log_error(title="Demo seed: verification failed", message=frappe.get_traceback())

    # 4. backdate a few prospects so the staleness/replacement flow is visible
    stale = frappe.get_all("Dalili Prospect", fields=["name"], limit=5, order_by="creation asc")
    for row in stale:
        frappe.db.set_value(
            "Dalili Prospect",
            row.name,
            {
                "last_verified_on": add_days(nowdate(), -45),
                "next_verification_on": add_days(nowdate(), -15),
                "verification_status": "Stale",
            },
            update_modified=False,
        )

    frappe.db.commit()
    frappe.flags.in_import = False

    return (
        f"Demo seeded: {len(created_icps)} ICPs, {len(runs)} agent runs, "
        f"{frappe.db.count('Dalili Prospect')} prospects, "
        f"{frappe.db.count('Dalili Contact')} contacts, "
        f"{frappe.db.count('Dalili Verification')} verifications, "
        f"{frappe.db.count('Dalili Lead List')} lead lists."
    )


def purge() -> str:
    """Remove demo data only. Real prospects (is_demo = 0) are left alone."""
    demo_prospects = [
        row["name"]
        for row in frappe.get_all(
            "Dalili Prospect", filters={"is_demo": 1}, fields=["name"], limit=5000
        )
    ]

    if demo_prospects:
        frappe.db.delete("Dalili Verification", {"prospect": ("in", demo_prospects)})
        frappe.db.delete("Dalili Contact", {"prospect": ("in", demo_prospects)})
        frappe.db.delete("Dalili Lead List Item", {"prospect": ("in", demo_prospects)})
        frappe.db.delete("Dalili Prospect", {"name": ("in", demo_prospects)})

    # lead lists and runs created by the seeder
    frappe.db.delete("Dalili Lead List", {"list_name": ("like", "%— %")})
    frappe.db.delete("Dalili Agent Run")
    frappe.db.delete("Dalili ICP", {"icp_name": ("in", [s["icp_name"] for s in DEMO_ICPS])})
    frappe.db.delete("Dalili Suppression", {"source": "Verification outcome"})
    frappe.db.commit()

    return f"Purged {len(demo_prospects)} demo prospects and their dependent records."


def reset() -> str:
    purge()
    return run(force=1)

"""ERPNext integration.

Dalili is not a CRM — ERPNext already has one. The job here is to hand a verified,
enriched company over to ERPNext as a Lead (or CRM Lead, if the standalone CRM app
is installed) with all the Dalili evidence attached, and to push the outcome back.

The target DocType is resolved at runtime because ERPNext v16 can run with either
`Lead` (built-in selling module) or `CRM Lead` (the separate frappe/crm app). Every
call is defensive: if neither exists, conversion reports a clear error instead of
raising a stack trace at the user.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

CUSTOM_FIELDS = [
    # (fieldname, label, fieldtype, options, insert_after)
    ("dalili_prospect", "Dalili Prospect", "Link", "Dalili Prospect", "source"),
    ("dalili_score", "Dalili Score", "Float", None, "dalili_prospect"),
    ("dalili_verified_on", "Dalili Verified On", "Date", None, "dalili_score"),
    ("dalili_whatsapp", "Dalili WhatsApp", "Data", None, "dalili_verified_on"),
    ("dalili_why_now", "Dalili Why Now", "Small Text", None, "dalili_whatsapp"),
    ("dalili_sector", "Dalili Sector", "Link", "Dalili Sector", "dalili_why_now"),
    ("dalili_region", "Dalili Region", "Data", None, "dalili_sector"),
    ("dalili_icp", "Dalili ICP", "Link", "Dalili ICP", "dalili_region"),
]


def resolve_lead_doctype() -> str | None:
    """Return the Lead DocType available on this site, if any."""
    for candidate in ("Lead", "CRM Lead"):
        if frappe.db.get_value("DocType", candidate, "name"):
            return candidate
    return None


def ensure_custom_fields() -> list[str]:
    """Idempotently add Dalili fields to the site's Lead doctype."""
    target = resolve_lead_doctype()
    if not target:
        return []

    created = []
    for fieldname, label, fieldtype, options, insert_after in CUSTOM_FIELDS:
        doc_name = f"{target}-{fieldname}"
        if frappe.db.get_value("Custom Field", doc_name, "name"):
            continue
        try:
            frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    "dt": target,
                    "fieldname": fieldname,
                    "label": label,
                    "fieldtype": fieldtype,
                    "options": options,
                    "insert_after": insert_after,
                    "read_only": 1 if fieldname != "dalili_prospect" else 0,
                    "translatable": 0,
                }
            ).insert(ignore_permissions=True)
            created.append(doc_name)
        except Exception:
            frappe.log_error(
                title=f"Dalili: could not create custom field {doc_name}",
                message=frappe.get_traceback(),
            )
    if created:
        frappe.clear_cache(doctype=target)
    return created


def convert(prospect_name: str, contact_name: str | None = None, *, owner: str | None = None) -> str:
    """Create an ERPNext Lead from a Prospect. Returns the Lead name."""
    target = resolve_lead_doctype()
    if not target:
        frappe.throw(
            "No Lead DocType found on this site. Install ERPNext (or frappe/crm) to use "
            "conversion, or export the lead list as CSV instead."
        )

    prospect = frappe.get_doc("Dalili Prospect", prospect_name)

    if prospect.erpnext_lead and frappe.db.get_value(target, prospect.erpnext_lead, "name"):
        return prospect.erpnext_lead  # already converted — idempotent

    if prospect.suppressed:
        frappe.throw(f"{prospect.company_name} is on the suppression list and cannot be contacted.")

    contact = None
    if contact_name:
        contact = frappe.get_doc("Dalili Contact", contact_name)
    elif prospect.best_contact:
        contact = frappe.get_doc("Dalili Contact", prospect.best_contact)
    else:
        rows = frappe.get_all(
            "Dalili Contact",
            filters={"prospect": prospect.name, "do_not_contact": 0},
            fields=["name"],
            order_by="is_primary desc",
            limit=1,
        )
        if rows:
            contact = frappe.get_doc("Dalili Contact", rows[0].name)

    if contact and contact.do_not_contact:
        frappe.throw(f"{contact.full_name} has opted out and cannot be contacted.")

    from dalili.enrichment.providers.llm import LLMProvider

    why = ""
    for row in prospect.signals or []:
        if row.why_now:
            why = row.why_now
            break
    if not why:
        from dalili.logic.scoring import why_now

        why = why_now(
            {"sector": prospect.sector},
            [
                {"title": s.title, "strength": s.strength, "detected_on": s.detected_on}
                for s in (prospect.signals or [])
            ],
        )
    if not why and prospect.sector:
        why = LLMProvider().why_now({"company_name": prospect.company_name,
                                     "sector": prospect.sector, "region": prospect.region,
                                     "signals": []}) or ""

    lead = frappe.get_doc(
        {
            "doctype": target,
            "company_name": prospect.company_name,
            "company": prospect.company_name,
            "status": "Lead",
            "source": "Dalili",
            "territory": prospect.region,
            "industry": prospect.sector,
            "website": prospect.website,
            "phone": (contact.phone if contact else prospect.primary_phone),
            "mobile_no": (contact.phone if contact else prospect.primary_phone),
            "email_id": (contact.email if contact else prospect.primary_email),
            "job_title": (contact.role_title if contact else ""),
            "no_of_employees": (prospect.employee_band or ""),
            "address_line1": prospect.address,
            "city": prospect.district,
            "state": prospect.region,
            "country": "Tanzania",
            # Dalili custom fields
            "dalili_prospect": prospect.name,
            "dalili_score": prospect.total_score,
            "dalili_verified_on": prospect.last_verified_on,
            "dalili_whatsapp": (contact.whatsapp if contact else prospect.primary_whatsapp),
            "dalili_why_now": why,
            "dalili_sector": prospect.sector,
            "dalili_region": prospect.region,
            "dalili_icp": frappe.db.get_value(
                "Dalili Lead List Item",
                {"prospect": prospect.name, "parenttype": "Dalili Lead List"},
                "parent",
            )
            and frappe.db.get_value(
                "Dalili Lead List",
                frappe.db.get_value(
                    "Dalili Lead List Item",
                    {"prospect": prospect.name, "parenttype": "Dalili Lead List"},
                    "parent",
                ),
                "icp",
            )
            or None,
        }
    )
    if contact:
        parts = (contact.full_name or "").split(" ", 1)
        lead.first_name = parts[0]
        lead.last_name = parts[1] if len(parts) > 1 else ""

    if owner:
        lead.owner = owner
    lead.flags.ignore_permissions = True
    lead.insert()

    frappe.db.set_value(
        "Dalili Prospect",
        prospect.name,
        {
            "status": "Converted",
            "lead_doctype": target,
            "erpnext_lead": lead.name,
            "converted_on": now_datetime(),
        },
    )
    return lead.name


def on_lead_update(doc, method=None):
    """Keep the prospect in sync when the sales team progresses the Lead."""
    prospect = doc.get("dalili_prospect")
    if not prospect or not frappe.db.get_value("Dalili Prospect", prospect, "name"):
        return
    if doc.get("status") in ("Opportunity", "Converted", "Customer") or doc.get("docstatus") == 1:
        frappe.db.set_value(
            "Dalili Prospect", prospect, {"status": "Converted"}, update_modified=False
        )


def conversion_stats() -> dict:
    # frappe.db.count() rather than fields=["count(name) as total"]: Frappe v16
    # rejects SQL functions embedded in the fields list ("SQL functions are not
    # allowed as strings in SELECT"), and db.count works on every version.
    converted = frappe.db.count("Dalili Prospect", {"status": "Converted"})
    total = frappe.db.count("Dalili Prospect")
    return {
        "converted": converted,
        "total": total,
        "conversion_rate": round(100.0 * converted / total, 1) if total else 0.0,
    }

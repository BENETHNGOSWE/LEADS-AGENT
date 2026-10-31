"""Verification: the moat.

Anyone can scrape a list of company names. What nobody has in Tanzania is a record
of *which numbers actually answered, when, and who picked up*. That evidence only
exists because a customer made the call — which is precisely why it cannot be
scraped by a competitor or produced by a language model.

Rules enforced here:
  * every outcome updates the contact, the prospect and (optionally) the suppression list;
  * a bad lead triggers a free replacement when the policy is enabled;
  * a verified contact gets a next-check date, so freshness is a schedule, not a hope.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, now_datetime, nowdate

GOOD_OUTCOMES = {"Answered - verified"}
BAD_OUTCOMES = {"Wrong person", "Left company", "Disconnected", "Wrong number", "Do not call"}

OUTCOME_TO_CONTACT_STATUS = {
    "Answered - verified": "Verified",
    "Wrong person": "Wrong Person",
    "Left company": "Left Company",
    "Disconnected": "Disconnected",
    "Wrong number": "Disconnected",
    "Do not call": "Do Not Contact",
    "No answer": "Unverified",
}


def log(
    *,
    prospect: str,
    contact: str | None = None,
    method: str = "Outbound call",
    outcome: str = "Answered - verified",
    notes: str = "",
    verified_by: str | None = None,
    cost: float = 0.0,
) -> str:
    """Record a verification attempt and apply its consequences."""
    if not outcome:
        frappe.throw("Outcome is required")

    doc = frappe.get_doc(
        {
            "doctype": "Dalili Verification",
            "prospect": prospect,
            "contact": contact,
            "method": method,
            "outcome": outcome,
            "verified_on": now_datetime(),
            "verified_by": verified_by or frappe.session.user,
            "cost": cost,
            "evidence": notes,
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def apply_outcome(verification) -> None:
    """Called from the Verification controller after insert."""
    settings = frappe.get_cached_doc("Dalili Settings")
    sla = int(getattr(settings, "verification_sla_days", 30) or 30)
    today = nowdate()
    outcome = verification.outcome

    contact_status = OUTCOME_TO_CONTACT_STATUS.get(outcome)

    # ---- contact -------------------------------------------------------
    if verification.contact:
        updates = {
            "verification_status": contact_status or "Unverified",
            "verification_method": verification.method,
            "last_verified_on": today,
            "next_check_on": add_days(today, sla),
        }
        if outcome in GOOD_OUTCOMES:
            updates["confidence"] = 95
        elif outcome in BAD_OUTCOMES:
            updates["confidence"] = 10
        if outcome == "Do not call":
            updates["do_not_contact"] = 1

        frappe.db.set_value("Dalili Contact", verification.contact, updates)

        if outcome == "Do not call":
            _suppress_contact(verification.contact, reason="Opt-out")

    # ---- prospect ------------------------------------------------------
    all_contacts = frappe.get_all(
        "Dalili Contact",
        filters={"prospect": verification.prospect},
        fields=["name", "verification_status", "do_not_contact"],
    )
    verified = [c for c in all_contacts if c.verification_status == "Verified"]
    reachable = [c for c in all_contacts if not c.do_not_contact]

    if verified:
        status = "Verified"
    elif reachable:
        status = "Partial"
    else:
        status = "Failed"

    prospect_updates = {
        "verification_status": status,
        "last_verified_on": today,
        "next_verification_on": add_days(today, sla),
    }
    if status == "Verified":
        prospect_updates["status"] = "Verified"

    frappe.db.set_value("Dalili Prospect", verification.prospect, prospect_updates)

    # ---- replacement policy -------------------------------------------
    if settings.replace_bad_leads and outcome in BAD_OUTCOMES:
        _issue_replacement(verification)


def _suppress_contact(contact_name: str, *, reason: str = "Opt-out") -> None:
    row = frappe.db.get_value(
        "Dalili Contact", contact_name, ["phone", "whatsapp", "email", "full_name"], as_dict=True
    )
    if not row:
        return
    for suppression_type, value in (
        ("Phone", row.phone or row.whatsapp),
        ("Email", row.email),
    ):
        if not value:
            continue
        if frappe.db.get_value(
            "Dalili Suppression", {"suppression_type": suppression_type, "value": value, "is_active": 1}
        ):
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Dalili Suppression",
                "suppression_type": suppression_type,
                "value": value,
                "reason": reason if reason in ("Opt-out", "Complaint", "Regulatory", "Manual",
                                               "Bounced", "Customer request") else "Opt-out",
                "prospect": row.get("prospect") if isinstance(row, dict) else None,
                "contact": contact_name,
                "source": "Verification outcome",
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert()


def _issue_replacement(verification) -> None:
    """Swap a bad lead for the next best uncontacted prospect from the same ICP."""
    try:
        lead_list_name = frappe.db.get_value(
            "Dalili Lead List Item",
            {"prospect": verification.prospect, "parenttype": "Dalili Lead List"},
            "parent",
        )
        if not lead_list_name:
            return
        lead_list = frappe.get_doc("Dalili Lead List", lead_list_name)
        if lead_list.status in ("Archived",):
            return

        in_list = {row.prospect for row in lead_list.items}
        candidate = frappe.get_all(
            "Dalili Prospect",
            filters={
                "status": ("in", ["Scored", "Verified"]),
                "name": ("not in", list(in_list) or ["-"]),
            },
            fields=["name", "company_name", "total_score"],
            order_by="total_score desc",
            limit=1,
        )
        if not candidate:
            return
        row = candidate[0]
        contact = frappe.db.get_value(
            "Dalili Contact",
            {"prospect": row.name, "do_not_contact": 0},
            ["name", "full_name", "phone", "whatsapp"],
            as_dict=True,
        )
        lead_list.append(
            "items",
            {
                "prospect": row.name,
                "company_name": row.company_name,
                "rank": len(lead_list.items) + 1,
                "contact": (contact or {}).get("name"),
                "contact_name": (contact or {}).get("full_name") or "",
                "phone": (contact or {}).get("phone") or "",
                "whatsapp": (contact or {}).get("whatsapp") or "",
                "score": row.total_score,
                "why_now": "Replacement for a bad lead",
                "included": 1,
            },
        )
        lead_list.total_prospects = len(lead_list.items)
        lead_list.total_contacts = sum(1 for r in lead_list.items if r.contact)
        lead_list.flags.ignore_permissions = True
        lead_list.save()

        frappe.db.set_value("Dalili Verification", verification.name, {"replacement_issued": 1})
        frappe.msgprint(
            f"Bad lead replaced with {row.company_name}.", alert=True, indicator="green"
        )
    except Exception:
        # A replacement is a courtesy, never a reason to fail the verification.
        frappe.log_error(title="Dalili replacement failed", message=frappe.get_traceback())


def queue_stale_prospects() -> int:
    """Daily job: flag anything older than the SLA as stale."""
    settings = frappe.get_cached_doc("Dalili Settings")
    if not settings.auto_requeue_stale:
        return 0
    days = int(settings.queue_stale_after_days or 30)
    cutoff = add_days(nowdate(), -days)

    rows = frappe.get_all(
        "Dalili Prospect",
        filters={
            "status": ("in", ["Scored", "Verified", "Qualified"]),
            "next_verification_on": ("<", nowdate()),
        },
        fields=["name"],
        limit=500,
    )
    for row in rows:
        frappe.db.set_value(
            "Dalili Prospect",
            row.name,
            {"verification_status": "Stale"},
            update_modified=False,
        )
    return len(rows)


def verification_stats(*, days: int = 90) -> dict:
    """Feed the dashboard and the 'verified rate' promise."""
    # Grouped aggregate needs real SQL. Frappe v16 forbids "count(name) as total"
    # inside get_all's fields, so this is an explicit parameterised query — and
    # grouping by (outcome, method) keeps it valid under ONLY_FULL_GROUP_BY.
    rows = frappe.db.sql(
        """
        SELECT outcome, method, COUNT(*) AS total
        FROM `tabDalili Verification`
        WHERE verified_on >= %(cutoff)s
        GROUP BY outcome, method
        """,
        {"cutoff": add_days(nowdate(), -days)},
        as_dict=True,
    )
    total = sum(r["total"] for r in rows) or 0
    good = sum(r["total"] for r in rows if r["outcome"] in GOOD_OUTCOMES)
    bad = sum(r["total"] for r in rows if r["outcome"] in BAD_OUTCOMES)
    return {
        "total": total,
        "answered": good,
        "bad": bad,
        "verified_rate": round(100.0 * good / total, 1) if total else 0.0,
        "bad_rate": round(100.0 * bad / total, 1) if total else 0.0,
        "by_outcome": rows,
    }

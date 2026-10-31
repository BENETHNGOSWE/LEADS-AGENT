"""Whitelisted API — the surface the portal page, the Desk and any external client use.

Frappe v16 breaking change handled here: `@frappe.whitelist()` must declare its
HTTP methods explicitly, so every endpoint below states `methods=[...]`.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import nowdate

from dalili import brief as brief_builder
from dalili import integration, verification
from dalili.logic.icp import clarifying_questions, parse_prompt


def _settings():
    return frappe.get_cached_doc("Dalili Settings")


def _defaults() -> dict:
    settings = _settings()
    return {
        "region": settings.default_region or "Dar es Salaam",
        "target_count": settings.default_target_count or 50,
        "min_score": settings.min_score_default or 60,
    }


def _require_enabled():
    if not _settings().enabled:
        frappe.throw("Dalili is disabled. Enable it in Dalili Settings.")


# ---------------------------------------------------------------------------
# 1. The agent conversation
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def chat(message: str, icp: str | None = None) -> dict:
    """Parse a natural-language request and return a proposal the user confirms.

    Deliberately does NOT create anything: the agent proposes, the human confirms.
    A lead tool that silently spends credits on a misparsed request loses trust fast.
    """
    _require_enabled()
    message = (message or "").strip()
    if not message:
        frappe.throw("Please describe who you want to reach.")

    parsed = parse_prompt(message, _defaults())

    # Optional: let the LLM fill gaps the rules missed (never overrides the rules).
    settings = _settings()
    if settings.llm_enabled:
        try:
            from dalili.enrichment.providers.llm import LLMProvider

            refined = LLMProvider(settings=settings).parse_icp(message)
            for key in (
                "sector", "region", "district", "employee_band_min", "employee_band_max",
                "include_keywords", "exclude_keywords", "target_count",
                "seniority_preference", "preferred_department",
            ):
                if not parsed.get(key) and refined.get(key):
                    parsed[key] = refined[key]
            if not parsed.get("watch_signals") and refined.get("watch_signals"):
                parsed["watch_signals"] = refined["watch_signals"]
        except Exception:
            frappe.log_error(title="Dalili: LLM ICP refine failed", message=frappe.get_traceback())

    return {
        "message": message,
        "parsed": parsed,
        "questions": clarifying_questions(parsed),
        "ready": not clarifying_questions(parsed),
        "language": parsed.get("_language"),
    }


@frappe.whitelist(methods=["POST"])
def preview(message: str, limit: int = 5) -> dict:
    """Show a taste of the universe before the user commits to a run."""
    _require_enabled()
    parsed = parse_prompt(message, _defaults())
    filters = {
        "sector": parsed.get("sector") or "",
        "region": parsed.get("region") or "",
        "district": parsed.get("district") or "",
        "employee_band_min": parsed.get("employee_band_min"),
        "employee_band_max": parsed.get("employee_band_max"),
        "include_keywords": parsed.get("include_keywords") or "",
        "exclude_keywords": parsed.get("exclude_keywords") or "",
    }

    from dalili.enrichment.providers.base import load_providers
    from dalili.enrichment.waterfall import discover

    providers = [p for p in load_providers() if p.source_type != "LLM Research"]
    records, stats = discover(filters, providers, limit=max(1, min(int(limit) * 4, 40)))

    samples = []
    for record in records[: int(limit)]:
        samples.append(
            {
                "company_name": record.get("company_name"),
                "sector": record.get("sector"),
                "region": record.get("region"),
                "phone": record.get("primary_phone"),
                "signals": [s.get("title") for s in (record.get("signals") or [])][:2],
            }
        )

    return {
        "parsed": parsed,
        "samples": samples,
        "universe_estimate": len(records),
        "providers": stats.get("providers", []),
        "errors": stats.get("errors", []),
    }


# ---------------------------------------------------------------------------
# 2. ICPs and runs
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def create_icp(message: str, name: str | None = None, run_now: int = 1) -> dict:
    """Create an ICP from a prompt, optionally kicking off a run immediately."""
    _require_enabled()
    parsed = parse_prompt(message, _defaults())

    doc = frappe.get_doc(
        {
            "doctype": "Dalili ICP",
            "icp_name": name or parsed.get("icp_name") or "New ICP",
            "status": "Active",
            "prompt_text": message,
            "sector": parsed.get("sector"),
            "region": parsed.get("region"),
            "district": parsed.get("district"),
            "employee_band_min": parsed.get("employee_band_min"),
            "employee_band_max": parsed.get("employee_band_max"),
            "include_keywords": parsed.get("include_keywords"),
            "exclude_keywords": parsed.get("exclude_keywords"),
            "target_count": parsed.get("target_count") or 50,
            "min_score": parsed.get("min_score") or 60,
            "languages": parsed.get("languages") or "Both",
            "seniority_preference": parsed.get("seniority_preference") or "Any",
            "delivery_channel": "Desk",
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert()

    result = {"icp": doc.name, "message": message}
    if run_now:
        result["run"] = enqueue_run(doc.name)
    return result


@frappe.whitelist(methods=["POST"])
def enqueue_run(icp: str) -> str:
    _require_enabled()
    frappe.has_permission("Dalili ICP", "read", doc=icp, throw=True)

    run = frappe.get_doc(
        {
            "doctype": "Dalili Agent Run",
            "icp": icp,
            "status": "Queued",
            "triggered_by": frappe.session.user,
            "currency": _settings().default_currency or "TZS",
        }
    )
    run.flags.ignore_permissions = True
    run.insert()

    frappe.enqueue(
        "dalili.agent.tasks.run_agent",
        queue="long",
        timeout=3600,
        job_name=f"dalili-run-{run.name}",
        run_name=run.name,
    )
    return run.name


@frappe.whitelist(methods=["POST"])
def run_now(icp: str) -> dict:
    """Run synchronously (used by tests, the demo seeder and impatient users)."""
    _require_enabled()
    from dalili.agent.orchestrator import execute

    run_name = execute(icp, triggered_by=frappe.session.user)
    return get_run(run_name)


@frappe.whitelist(methods=["GET"])
def get_run(run: str) -> dict:
    doc = frappe.get_doc("Dalili Agent Run", run)
    return {
        "name": doc.name,
        "status": doc.status,
        "icp": doc.icp,
        "started_at": doc.started_at,
        "finished_at": doc.finished_at,
        "duration_seconds": doc.duration_seconds,
        "counters": {
            "discovered": doc.discovered,
            "duplicates_merged": doc.duplicates_merged,
            "enriched": doc.enriched,
            "scored": doc.scored,
            "qualified": doc.qualified,
            "delivered": doc.delivered,
        },
        "lead_list": doc.lead_list,
        "error_log": doc.error_log,
        "steps": [
            {
                "sequence": s.sequence,
                "step": s.step_name,
                "status": s.status,
                "in": s.records_in,
                "out": s.records_out,
                "log": s.log,
            }
            for s in doc.steps
        ],
    }


# ---------------------------------------------------------------------------
# 3. Lists, briefs, exports
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_briefs(limit: int = 20) -> list:
    return frappe.get_all(
        "Dalili Lead List",
        fields=["name", "list_name", "icp", "generated_on", "total_prospects",
                "verified_count", "avg_score", "status"],
        order_by="generated_on desc",
        limit=int(limit),
    )


@frappe.whitelist(methods=["GET"])
def get_brief(lead_list: str, channel: str = "text") -> dict:
    """channel: text (WhatsApp), html (print), csv (CRM)."""
    doc = frappe.get_doc("Dalili Lead List", lead_list)
    payload = {
        "name": doc.name,
        "list_name": doc.list_name,
        "icp": doc.icp,
        "generated_on": doc.generated_on,
        "total_prospects": doc.total_prospects,
        "verified_count": doc.verified_count,
        "avg_score": doc.avg_score,
        "status": doc.status,
    }
    if channel == "html":
        payload["content"] = brief_builder.build_html(lead_list)
    elif channel == "csv":
        payload["content"] = brief_builder.build_csv(lead_list)
    else:
        payload["content"] = brief_builder.build_text(lead_list)
    return payload


@frappe.whitelist(methods=["GET", "POST"])
def export_csv(lead_list: str) -> dict:
    content = brief_builder.build_csv(lead_list)
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": f"{lead_list}.csv",
            "content": content,
            "is_private": 1,
            "attached_to_doctype": "Dalili Lead List",
            "attached_to_name": lead_list,
        }
    )
    file_doc.flags.ignore_permissions = True
    file_doc.insert()
    return {"file_url": file_doc.file_url, "rows": content.count("\n") - 1}


@frappe.whitelist(methods=["POST"])
def mark_delivered(lead_list: str, channel: str = "WhatsApp", to: str = "") -> dict:
    frappe.db.set_value(
        "Dalili Lead List",
        lead_list,
        {"status": "Delivered", "delivery_channel": channel, "delivered_to": to,
         "delivered_on": frappe.utils.now_datetime()},
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# 4. Verification loop (the moat)
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def log_verification(
    prospect: str,
    contact: str | None = None,
    method: str = "Outbound call",
    outcome: str = "Answered - verified",
    notes: str = "",
) -> dict:
    _require_enabled()
    name = verification.log(
        prospect=prospect, contact=contact, method=method, outcome=outcome,
        notes=notes, verified_by=frappe.session.user,
    )
    return {"verification": name, "outcome": outcome}


@frappe.whitelist(methods=["GET"])
def verification_summary(days: int = 90) -> dict:
    return verification.verification_stats(days=int(days))


# ---------------------------------------------------------------------------
# 5. Conversion, suppression, imports
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def convert(prospect: str, contact: str | None = None) -> dict:
    lead = integration.convert(prospect, contact)
    return {"lead": lead, "prospect": prospect}


@frappe.whitelist(methods=["POST"])
def suppress(value: str, suppression_type: str = "Phone", reason: str = "Manual",
             notes: str = "") -> dict:
    doc = frappe.get_doc(
        {
            "doctype": "Dalili Suppression",
            "suppression_type": suppression_type,
            "value": value,
            "reason": reason if reason in ("Opt-out", "Complaint", "Regulatory", "Manual",
                                           "Bounced", "Customer request") else "Manual",
            "notes": notes,
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert()
    return {"suppression": doc.name}


@frappe.whitelist(methods=["POST"])
def import_registry_csv(content: str, source_name: str = "Company Register") -> dict:
    """Import a BRELA/TRA-ish CSV as prospects. Returns a summary."""
    from dalili.enrichment.providers.registry import parse_csv
    from dalili.logic.identity import match_key

    records, warnings = parse_csv(content)
    created, merged = 0, 0
    for record in records:
        key = match_key(
            brela_number=record.get("brela_number"), tin=record.get("tin"),
            domain=record.get("domain"), phone=record.get("primary_phone"),
            name=record.get("company_name"),
        )
        existing = frappe.db.get_value("Dalili Prospect", {"normalized_key": key}, "name")
        if existing:
            merged += 1
            continue
        record["normalized_key"] = key
        doc = frappe.get_doc({"doctype": "Dalili Prospect", **record})
        doc.flags.ignore_permissions = True
        doc.insert()
        created += 1

    return {"created": created, "merged": merged, "rows": len(records), "warnings": warnings[:20]}


# ---------------------------------------------------------------------------
# 6. Dashboard numbers
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def stats() -> dict:
    def count(doctype, filters=None):
        return frappe.db.count(doctype, filters or {})

    settings = _settings()
    total = count("Dalili Prospect")
    verified = count("Dalili Prospect", {"verification_status": "Verified"})
    stale = count("Dalili Prospect", {"verification_status": "Stale"})
    return {
        "prospects": total,
        "verified": verified,
        "stale": stale,
        "verified_rate": round(100.0 * verified / total, 1) if total else 0.0,
        "contacts": count("Dalili Contact"),
        # Contact-level is the honest headline: a company with 3 contacts and 1
        # verified number is perfectly callable, but counts as "unverified" at
        # prospect level. Both numbers are returned, labelled separately.
        "verified_contacts": count("Dalili Contact", {"verification_status": "Verified"}),
        "icps": count("Dalili ICP", {"status": "Active"}),
        "runs": count("Dalili Agent Run"),
        "lead_lists": count("Dalili Lead List"),
        "conversions": integration.conversion_stats(),
        "verification": verification.verification_stats(days=90),
        "demo_mode": bool(settings.demo_mode),
        "today": nowdate(),
    }


@frappe.whitelist(methods=["GET"])
def sectors() -> list:
    return frappe.get_all(
        "Dalili Sector", filters={"is_active": 1}, fields=["name", "sector_group"],
        order_by="sector_name asc",
    )


@frappe.whitelist(methods=["GET"])
def signal_types() -> list:
    return frappe.get_all(
        "Dalili Signal Type", filters={"is_active": 1},
        fields=["name", "category", "weight"], order_by="weight desc",
    )

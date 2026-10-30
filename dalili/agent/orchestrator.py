"""The lead agent.

Pipeline (each stage is recorded as a step on the Agent Run so a user can see
exactly what happened and where the time went):

    1. resolve     ICP -> filters
    2. discover    query providers
    3. dedupe      entity resolution against the database and within the batch
    4. upsert      create/update Prospect records
    5. enrich      waterfall fill of missing fields
    6. signals     attach buying signals
    7. contacts    attach people with contact points
    8. score       explainable fit/signal/confidence/contactability
    9. select      rank, trim to target_count above min_score
   10. list        create the Dalili Lead List the customer actually receives

Design notes
------------
* Everything is idempotent: running the same ICP twice merges into existing
  prospects rather than duplicating them (that is the entity graph compounding).
* One bad record never kills a run; each record is processed in its own try/except
  and the failure is written to the step log.
* The run is executed on the `long` queue so a 200-record run does not block a
  web request.
"""

from __future__ import annotations

import json
import traceback

import frappe
from frappe.utils import add_days, now_datetime, time_diff_in_seconds

from dalili.enrichment.waterfall import discover, enrich_record
from dalili.logic.identity import find_duplicate, match_key
from dalili.logic.normalize import domain_from_website, normalize_phone
from dalili.logic.scoring import score_prospect, why_now

MAX_UPSERT_PER_RUN = 400


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _safe_link(doctype: str, value):
    """Return `value` if it exists as a document, else None.

    Demo/dev data must never hard-fail because a Link target is missing — a broken
    link on 200 records would abort the whole run.
    """
    if not value:
        return None
    try:
        if frappe.db.get_value(doctype, value, "name"):
            return value
    except Exception:
        return None
    return None


def _settings_weights(settings) -> dict:
    return {
        "fit": getattr(settings, "weight_fit", 35),
        "signal": getattr(settings, "weight_signal", 30),
        "confidence": getattr(settings, "weight_confidence", 20),
        "contactability": getattr(settings, "weight_contactability", 15),
    }


class StepRecorder:
    """Appends steps to the run document as the pipeline progresses."""

    def __init__(self, run_doc):
        self.run = run_doc
        self.sequence = 0
        self._current = None

    def begin(self, name: str, records_in: int = 0):
        self.sequence += 1
        self._current = {
            "sequence": self.sequence,
            "step_name": name,
            "status": "Running",
            "records_in": records_in,
            "started_at": now_datetime(),
        }
        self.run.append("steps", self._current)
        self.run.save(ignore_permissions=True)
        return self._current

    def end(self, records_out: int = 0, log: str = "", status: str = "Completed"):
        if not self._current:
            return
        row = self.run.steps[-1]
        row.status = status
        row.records_out = records_out
        row.finished_at = now_datetime()
        row.log = (log or "")[:2000]
        self._current = None
        self.run.save(ignore_permissions=True)

    def skipped(self, name: str, reason: str):
        self.sequence += 1
        self.run.append(
            "steps",
            {
                "sequence": self.sequence,
                "step_name": name,
                "status": "Skipped",
                "finished_at": now_datetime(),
                "log": reason[:2000],
            },
        )
        self.run.save(ignore_permissions=True)


def _icp_filters(icp) -> dict:
    return {
        "sector": icp.sector or "",
        "region": icp.region or "",
        "district": icp.district or "",
        "employee_band_min": icp.employee_band_min,
        "employee_band_max": icp.employee_band_max,
        "include_keywords": icp.include_keywords or "",
        "exclude_keywords": icp.exclude_keywords or "",
        "target_count": icp.target_count or 50,
        "min_score": icp.min_score or 60,
        "watch_signals": [row.signal_type for row in (icp.watch_signals or []) if row.signal_type],
    }


def _prospect_payload(record: dict, icp) -> dict:
    website = record.get("website") or ""
    domain = record.get("domain") or domain_from_website(website)
    phone = normalize_phone(record.get("primary_phone"))
    whatsapp = normalize_phone(record.get("primary_whatsapp")) or phone

    return {
        "company_name": (record.get("company_name") or "").strip()[:140],
        "legal_name": record.get("legal_name") or "",
        "sector": _safe_link("Dalili Sector", record.get("sector") or icp.sector),
        "sub_sector": record.get("sub_sector") or "",
        "region": record.get("region") or icp.region or "",
        "district": record.get("district") or "",
        "ward": record.get("ward") or "",
        "address": record.get("address") or "",
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "primary_phone": phone,
        "primary_whatsapp": whatsapp,
        "primary_email": (record.get("primary_email") or "").lower(),
        "website": website,
        "domain": domain,
        "employee_band": record.get("employee_band") or "",
        "revenue_band": record.get("revenue_band") or "",
        "founded_year": record.get("founded_year") or None,
        "brela_number": record.get("brela_number") or "",
        "tin": record.get("tin") or "",
        "vat_number": record.get("vat_number") or "",
        "normalized_key": match_key(
            brela_number=record.get("brela_number"),
            tin=record.get("tin"),
            domain=domain,
            phone=phone,
            name=record.get("company_name"),
            default_cc=frappe.db.get_single_value("Dalili Settings", "phone_country_code") or "255",
        ),
    }


def _upsert_prospect(payload: dict, *, existing_names: list[str]) -> tuple[str, bool]:
    """Create or merge a prospect. Returns (name, was_created)."""
    key = payload.get("normalized_key")

    if key:
        name = frappe.db.get_value("Dalili Prospect", {"normalized_key": key}, "name")
        if name:
            _fill_blanks("Dalili Prospect", name, payload)
            return name, False

    # Fuzzy match against this sector's existing records (entity resolution).
    candidates = frappe.get_all(
        "Dalili Prospect",
        filters={"sector": payload.get("sector") or ""} if payload.get("sector") else {},
        fields=["name", "company_name", "domain", "primary_phone", "brela_number", "tin"],
        limit=500,
    )
    idx, score, reason = find_duplicate(payload, candidates, threshold=0.88)
    if idx is not None:
        target = candidates[idx]["name"]
        _fill_blanks("Dalili Prospect", target, payload)
        frappe.get_doc("Dalili Prospect", target).add_comment(
            "Info", f"Merged duplicate from agent run ({reason}, score {score})"
        )
        return target, False

    doc = frappe.get_doc({"doctype": "Dalili Prospect", **payload})
    doc.flags.ignore_permissions = True
    doc.insert()
    existing_names.append(doc.name)
    return doc.name, True


def _fill_blanks(doctype: str, name: str, payload: dict):
    """Only write fields that are currently empty — never overwrite verified data."""
    current = frappe.db.get_value(doctype, name, list(payload.keys()), as_dict=True) or {}
    updates = {
        field: value
        for field, value in payload.items()
        if value not in (None, "", 0) and (current.get(field) in (None, "", 0))
    }
    if updates:
        frappe.db.set_value(doctype, name, updates, update_modified=False)


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def execute(icp_name: str, triggered_by: str | None = None,
            existing_run: str | None = None) -> str:
    """Run the full pipeline synchronously. Returns the Agent Run name.

    `existing_run` lets the queued job reuse the "Queued" run document that
    api.enqueue_run already created, so the user polls one record, not two.
    """
    icp = frappe.get_doc("Dalili ICP", icp_name)
    settings = frappe.get_cached_doc("Dalili Settings")
    filters = _icp_filters(icp)

    if existing_run and frappe.db.get_value("Dalili Agent Run", existing_run, "name"):
        run = frappe.get_doc("Dalili Agent Run", existing_run)
        run.status = "Running"
        run.started_at = now_datetime()
        run.triggered_by = run.triggered_by or triggered_by or frappe.session.user
        run.filters_snapshot = json.dumps(filters, indent=1, default=str)
        run.steps = []
        run.flags.ignore_permissions = True
        run.save()
    else:
        run = frappe.get_doc(
            {
                "doctype": "Dalili Agent Run",
                "icp": icp.name,
                "status": "Running",
                "started_at": now_datetime(),
                "triggered_by": triggered_by or frappe.session.user,
                "currency": settings.default_currency or "TZS",
                "filters_snapshot": json.dumps(filters, indent=1, default=str),
            }
        )
        run.flags.ignore_permissions = True
        run.insert()
    steps = StepRecorder(run)

    counters = {
        "discovered": 0, "duplicates_merged": 0, "enriched": 0,
        "scored": 0, "qualified": 0, "delivered": 0, "cost": 0.0,
        "verification_required": 0,
    }

    try:
        from dalili.enrichment.providers.base import load_providers

        providers = load_providers()

        # -- 1. discover ---------------------------------------------------
        steps.begin("Discover candidates", 0)
        limit = min(MAX_UPSERT_PER_RUN, (icp.target_count or 50) * 6)
        records, disc_stats = discover(filters, providers, limit=limit)
        counters["discovered"] = len(records)
        counters["cost"] += disc_stats["cost"]
        steps.end(
            len(records),
            log=(
                f"providers: {', '.join(disc_stats['providers']) or 'none'}\n"
                f"calls: {disc_stats['calls']}, cost: {disc_stats['cost']:.2f}\n"
                + ("\nerrors:\n" + "\n".join(disc_stats["errors"]) if disc_stats["errors"] else "")
            ),
        )

        if not records:
            raise RuntimeError(
                "No candidates found. In Demo Mode check that Dalili Settings.demo_mode is "
                "enabled; otherwise configure an API key on a Dalili Data Source."
            )

        # -- 2. dedupe within the batch ------------------------------------
        steps.begin("Entity resolution (batch)", len(records))
        unique, merged = [], 0
        for record in records:
            idx, score, _ = find_duplicate(record, unique, threshold=0.88)
            if idx is None:
                unique.append(record)
            else:
                for field, value in record.items():
                    if value not in (None, "", 0) and unique[idx].get(field) in (None, "", 0):
                        unique[idx][field] = value
                merged += 1
        counters["duplicates_merged"] += merged
        steps.end(len(unique), log=f"{merged} duplicate(s) merged inside the batch")

        # -- 3. upsert -----------------------------------------------------
        steps.begin("Create / merge prospects", len(unique))
        prospect_names: list[str] = []
        record_by_name: dict[str, dict] = {}
        created = 0
        errors = []
        for record in unique:
            try:
                payload = _prospect_payload(record, icp)
                if not payload["company_name"]:
                    continue
                name, was_created = _upsert_prospect(payload, existing_names=prospect_names)
                created += 1 if was_created else 0
                if name not in prospect_names:
                    prospect_names.append(name)
                record_by_name[name] = record
                frappe.db.set_value("Dalili Prospect", name, {"is_demo": 1 if record.get("source_type") == "Manual" else 0}, update_modified=False)
            except Exception as exc:
                errors.append(f"{record.get('company_name')}: {exc}")
        steps.end(
            len(prospect_names),
            log=f"{created} new, {len(prospect_names) - created} merged\n"
                + ("\n".join(errors[:10]) if errors else ""),
        )

        # -- 4. enrich + signals + contacts + score ------------------------
        steps.begin("Enrich, score and attach evidence", len(prospect_names))
        qualified_rows = []
        weights = _settings_weights(settings)
        decay = getattr(settings, "signal_decay_days", 90) or 90
        for name in prospect_names:
            try:
                record = record_by_name.get(name, {})
                prospect = frappe.get_doc("Dalili Prospect", name)
                current = prospect.as_dict()

                enriched, source_refs, stats = enrich_record(
                    {**record, **{k: current.get(k) for k in
                                  ("primary_phone", "primary_email", "website", "domain",
                                   "employee_band", "region", "district", "sector")
                                  if current.get(k)}},
                    providers,
                )
                counters["cost"] += stats["cost"]
                if stats["providers_used"]:
                    counters["enriched"] += 1

                _write_sources(prospect, source_refs)
                _write_signals(prospect, record.get("signals") or [])
                _write_contacts(prospect, record.get("contacts") or [])

                # refresh from DB so scoring sees what was just written
                prospect.reload()
                contacts = _load_contacts(name)

                signals = [
                    {
                        "title": s.title,
                        "signal_type": s.signal_type,
                        "strength": s.strength,
                        "detected_on": s.detected_on,
                    }
                    for s in prospect.signals
                ]
                sources = [
                    {
                        "source_label": s.source_label,
                        "source_type": s.source_type,
                        "confidence": s.confidence,
                        "retrieved_on": s.retrieved_on,
                    }
                    for s in prospect.sources
                ]

                result = score_prospect(
                    {
                        "company_name": prospect.company_name,
                        "legal_name": prospect.legal_name,
                        "sector": prospect.sector,
                        "sub_sector": prospect.sub_sector,
                        "region": prospect.region,
                        "district": prospect.district,
                        "ward": prospect.ward,
                        "address": prospect.address,
                        "employee_band": prospect.employee_band,
                        "revenue_band": prospect.revenue_band,
                        "founded_year": prospect.founded_year,
                    },
                    {
                        "sector": filters["sector"],
                        "region": filters["region"],
                        "district": filters["district"],
                        "employee_band_min": filters["employee_band_min"],
                        "employee_band_max": filters["employee_band_max"],
                        "include_keywords": filters["include_keywords"],
                        "exclude_keywords": filters["exclude_keywords"],
                    },
                    contacts=contacts,
                    signals=signals,
                    sources=sources,
                    weights=weights,
                    decay_days=decay,
                )
                counters["scored"] += 1

                best_contact = _best_contact_name(contacts, name)
                frappe.db.set_value(
                    "Dalili Prospect",
                    name,
                    {
                        "total_score": result["total"],
                        "fit_score": result["components"]["fit"],
                        "signal_score": result["components"]["signal"],
                        "confidence_score": result["components"]["confidence"],
                        "contactability_score": result["components"]["contactability"],
                        "score_breakdown": json.dumps(result, indent=1, default=str),
                        "signal_count": len(signals),
                        "verified_contacts": sum(
                            1 for c in contacts if c.get("verification_status") == "Verified"
                        ),
                        "best_contact": best_contact,
                        "status": "Scored" if not result.get("excluded") else "Disqualified",
                        "next_verification_on": add_days(
                            frappe.utils.nowdate(),
                            getattr(settings, "verification_sla_days", 30) or 30,
                        ),
                    },
                    update_modified=True,
                )

                if result.get("excluded"):
                    continue
                if result["total"] >= (filters["min_score"] or 60):
                    qualified_rows.append(
                        {
                            "name": name,
                            "company_name": prospect.company_name,
                            "score": result["total"],
                            "contact": best_contact,
                            "why_now": why_now(
                                {"sector": prospect.sector}, signals
                            ),
                        }
                    )
            except Exception as exc:
                errors.append(f"{name}: {exc}\n{traceback.format_exc()[:600]}")

        steps.end(
            len(qualified_rows),
            log=f"{len(qualified_rows)} qualified above score {filters['min_score']}\n"
                + ("\n".join(errors[:6]) if errors else ""),
        )

        # -- 5. build the list ---------------------------------------------
        steps.begin("Build lead list", len(qualified_rows))
        qualified_rows.sort(key=lambda r: r["score"], reverse=True)
        target = min(int(icp.target_count or 50), int(settings.max_leads_per_list or 200))
        selected = qualified_rows[:target]
        counters["qualified"] = len(qualified_rows)

        lead_list = frappe.get_doc(
            {
                "doctype": "Dalili Lead List",
                "list_name": f"{icp.icp_name} — {frappe.utils.formatdate(frappe.utils.nowdate())}",
                "icp": icp.name,
                "status": "Ready",
                "generated_on": now_datetime(),
                "agent_run": run.name,
                "criteria_snapshot": json.dumps(filters, indent=1, default=str),
            }
        )
        for rank, row in enumerate(selected, start=1):
            contact = frappe.db.get_value(
                "Dalili Contact", row["contact"], ["full_name", "phone", "whatsapp"], as_dict=True
            ) if row["contact"] else None
            lead_list.append(
                "items",
                {
                    "prospect": row["name"],
                    "company_name": row["company_name"],
                    "rank": rank,
                    "contact": row["contact"],
                    "contact_name": (contact or {}).get("full_name") or "",
                    "phone": (contact or {}).get("phone") or "",
                    "whatsapp": (contact or {}).get("whatsapp") or "",
                    "score": row["score"],
                    "why_now": row["why_now"],
                    "included": 1,
                },
            )
        lead_list.flags.ignore_permissions = True
        lead_list.insert()
        _recalculate_list(lead_list)
        counters["delivered"] = len(selected)

        frappe.db.set_value(
            "Dalili ICP",
            icp.name,
            {
                "last_run_on": now_datetime(),
                "total_leads_delivered": (icp.total_leads_delivered or 0) + len(selected),
            },
        )
        steps.end(len(selected), log=f"Lead list {lead_list.name} created")

        duration = time_diff_in_seconds(now_datetime(), run.started_at)
        run.reload()
        run.update(
            {
                "status": "Completed",
                "finished_at": now_datetime(),
                "duration_seconds": duration,
                "discovered": counters["discovered"],
                "duplicates_merged": counters["duplicates_merged"],
                "enriched": counters["enriched"],
                "scored": counters["scored"],
                "qualified": counters["qualified"],
                "delivered": counters["delivered"],
                "verification_required": sum(
                    1 for row in selected
                    if not frappe.db.get_value("Dalili Prospect", row["name"], "last_verified_on")
                ),
                "cost_estimate": counters["cost"],
                "lead_list": lead_list.name,
                "error_log": "\n".join(errors[:20]),
            }
        )
        run.flags.ignore_permissions = True
        run.save()
        return run.name

    except Exception as exc:
        run.reload()
        run.status = "Failed"
        run.finished_at = now_datetime()
        run.error_log = f"{exc}\n\n{traceback.format_exc()[:4000]}"
        run.flags.ignore_permissions = True
        run.save()
        steps.end(0, log=str(exc), status="Failed")
        frappe.log_error(title="Dalili agent run failed", message=run.error_log)
        raise


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------
def _write_sources(prospect, source_refs: list[dict]):
    seen = {(row.source_label or "") for row in (prospect.sources or [])}
    for ref in source_refs:
        if (ref.get("source_label") or "") in seen:
            continue
        prospect.append("sources", ref)
        seen.add(ref.get("source_label") or "")
    prospect.flags.ignore_permissions = True
    prospect.flags.ignore_links = True
    prospect.flags.ignore_mandatory = True
    prospect.save()


def _write_signals(prospect, signals: list[dict]):
    existing = {(row.signal_type or "", row.title or "") for row in (prospect.signals or [])}
    for sig in signals:
        key = (sig.get("signal_type") or "", sig.get("title") or "")
        if key in existing:
            continue
        prospect.append(
            "signals",
            {
                "signal_type": _safe_link("Dalili Signal Type", sig.get("signal_type")),
                "title": sig.get("title") or sig.get("signal_type") or "Signal",
                "category": sig.get("category") or "",
                "detected_on": sig.get("detected_on"),
                "strength": sig.get("strength") or 0,
                "evidence_url": sig.get("evidence_url") or "",
                "why_now": sig.get("why_now") or "",
            },
        )
    prospect.flags.ignore_permissions = True
    prospect.save()


def _write_contacts(prospect, contacts: list[dict]):
    for person in contacts or []:
        if not person.get("full_name"):
            continue
        phone = normalize_phone(person.get("phone"))
        exists = frappe.db.get_value(
            "Dalili Contact",
            {"prospect": prospect.name, "full_name": person["full_name"]},
            "name",
        )
        if exists:
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Dalili Contact",
                "prospect": prospect.name,
                "full_name": person["full_name"],
                "role_title": person.get("role_title") or "",
                "department": person.get("department") or "",
                "seniority": person.get("seniority") or "Unknown",
                "phone": phone,
                "whatsapp": normalize_phone(person.get("whatsapp")),
                "email": (person.get("email") or "").lower(),
                "language": person.get("language") or "Swahili",
                "is_primary": person.get("is_primary") or 0,
                "consent_basis": person.get("consent_basis") or "Public business listing",
                "confidence": 55,
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert()


def _load_contacts(prospect_name: str) -> list[dict]:
    rows = frappe.get_all(
        "Dalili Contact",
        filters={"prospect": prospect_name},
        fields=["full_name", "seniority", "whatsapp", "phone", "email",
                "verification_status", "consent_basis", "do_not_contact"],
    )
    return rows


def _best_contact_name(contacts: list[dict], prospect_name: str) -> str | None:
    """Pick the reachable, senior, non-opted-out contact."""
    order = {"Owner / Founder": 5, "C-Level": 4, "Director": 3, "Manager": 2, "Officer": 1}
    best, best_score = None, -1
    for contact in contacts:
        if contact.get("do_not_contact"):
            continue
        score = order.get(contact.get("seniority") or "Unknown", 0) * 10
        if contact.get("whatsapp"):
            score += 15
        if contact.get("verification_status") == "Verified":
            score += 20
        if score > best_score:
            best_score = score
            best = contact.get("full_name")
    if best:
        return frappe.db.get_value(
            "Dalili Contact",
            {"prospect": prospect_name, "full_name": best},
            "name",
        )
    return None


def _recalculate_list(lead_list):
    rows = lead_list.items or []
    scores = [row.score for row in rows if row.score]
    lead_list.total_prospects = len(rows)
    lead_list.total_contacts = sum(1 for row in rows if row.contact)
    lead_list.verified_count = sum(1 for row in rows if row.verified_on)
    lead_list.avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    lead_list.flags.ignore_permissions = True
    lead_list.save()

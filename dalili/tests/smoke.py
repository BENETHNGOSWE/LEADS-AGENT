"""Read-mostly smoke test — run this on a live bench before clicking around.

    bench --site <site> execute dalili.tests.smoke.run_all

Every check is executed independently, so one failure does not hide the next.
The point is to surface *all* remaining breakage in a single run instead of
discovering it one browser click at a time.

Design notes:
* Checks are ordered cheapest-and-purest first, so a total failure still tells
  you something.
* Anything that writes is marked and kept last: `export_csv` creates a private
  File, `preview` may call the discovery provider.
* Nothing here deletes data, submits documents, or sends messages.
"""

from __future__ import annotations

import traceback

import frappe

RESULTS: list[tuple[str, str, str]] = []


def _check(label: str, fn, *, writes: bool = False):
    """Run one check, record PASS/FAIL, never raise."""
    try:
        value = fn()
        detail = "" if value is None else str(value)[:220]
        RESULTS.append(("PASS", label + (" [writes]" if writes else ""), detail))
    except Exception as exc:  # noqa: BLE001 - a smoke test reports, never crashes
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        RESULTS.append(("FAIL", label, f"{exc.__class__.__name__}: {first_line}"[:300]))
        if frappe.flags.get("dalili_smoke_traceback"):
            traceback.print_exc()


def _first_lead_list() -> str:
    rows = frappe.get_all("Dalili Lead List", fields=["name"], order_by="creation desc", limit=1)
    if not rows:
        raise AssertionError("no lead lists — run dalili.demo.seed.run first")
    return rows[0]["name"]


def _first_run() -> str:
    rows = frappe.get_all("Dalili Agent Run", fields=["name"], order_by="creation desc", limit=1)
    if not rows:
        raise AssertionError("no agent runs — run dalili.demo.seed.run first")
    return rows[0]["name"]


def _first_prospect() -> str:
    rows = frappe.get_all("Dalili Prospect", fields=["name"], order_by="creation desc", limit=1)
    if not rows:
        raise AssertionError("no prospects — run dalili.demo.seed.run first")
    return rows[0]["name"]


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
def _seed_data():
    counts = {
        "sectors": frappe.db.count("Dalili Sector"),
        "signal_types": frappe.db.count("Dalili Signal Type"),
        "data_sources": frappe.db.count("Dalili Data Source"),
        "icps": frappe.db.count("Dalili ICP"),
        "prospects": frappe.db.count("Dalili Prospect"),
        "contacts": frappe.db.count("Dalili Contact"),
        "lead_lists": frappe.db.count("Dalili Lead List"),
    }
    missing = [k for k, v in counts.items() if not v]
    if missing:
        raise AssertionError(f"empty: {missing} | counts={counts}")
    return counts


def _roles():
    roles = set(frappe.get_all("Role", filters={"name": ("like", "Dalili%")}, pluck="name"))
    want = {"Dalili Manager", "Dalili Agent"}
    if not want.issubset(roles):
        raise AssertionError(f"missing roles: {want - roles}")
    return sorted(roles)


def _settings():
    fields = {
        "enable_portal": "enable_portal",
        "min_score_default": "min_score_default",
        "country": "country",
    }
    return {k: frappe.db.get_single_value("Dalili Settings", v) for k, v in fields.items()}


def _parser():
    from dalili.logic.icp import parse_prompt

    parsed = parse_prompt(
        "Nipe kampuni 12 za hoteli Dar es Salaam zenye wafanyakazi zaidi ya 20", {}
    )
    if not parsed.get("sector") or not parsed.get("region"):
        raise AssertionError(f"parser returned {parsed}")
    return {"sector": parsed["sector"], "region": parsed["region"],
            "min_employees": parsed["employee_band_min"]}


def _scoring():
    from dalili.logic.scoring import score_prospect

    out = score_prospect(
        {"company_name": "Smoke Test Hotel", "sector": "Hospitality & Tourism",
         "region": "Dar es Salaam", "employee_band": "51-200"},
        {"sector": "Hospitality & Tourism", "region": "Dar es Salaam"},
    )
    return {"total": out["total"], "fit": out["components"]["fit"]}


def _api_stats():
    from dalili.api import stats

    out = stats()
    return {k: out[k] for k in list(out)[:5]}


def _api_sectors():
    from dalili.api import sectors

    return f"{len(sectors())} sectors"


def _api_signal_types():
    from dalili.api import signal_types

    return f"{len(signal_types())} signal types"


def _api_chat():
    from dalili.api import chat

    out = chat("Nipe kampuni 10 za hoteli Dar es Salaam zenye wafanyakazi zaidi ya 20")
    return {"icp_name": out.get("icp", {}).get("icp_name") or out.get("icp_name")}


def _api_list_briefs():
    from dalili.api import list_briefs

    rows = list_briefs(limit=5)
    return f"{len(rows)} briefs"


def _api_get_run():
    from dalili.api import get_run

    out = get_run(_first_run())
    return {"status": out.get("status"), "delivered": out.get("delivered")}


def _brief_text():
    from dalili.brief import build_text

    text = build_text(_first_lead_list())
    if not text or len(text) < 50:
        raise AssertionError(f"brief suspiciously short: {len(text or '')} chars")
    return f"{len(text)} chars"


def _brief_html():
    from dalili.brief import build_html

    html = build_html(_first_lead_list())
    if "<" not in html:
        raise AssertionError("html brief has no markup")
    return f"{len(html)} chars"


def _brief_csv():
    from dalili.brief import build_csv

    csv_text = build_csv(_first_lead_list())
    lines = csv_text.strip().splitlines()
    if len(lines) < 2:
        raise AssertionError(f"csv has {len(lines)} line(s)")
    return f"{len(lines) - 1} rows"


def _api_get_brief():
    from dalili.api import get_brief

    out = get_brief(_first_lead_list(), channel="text")
    return list(out)[:4]


def _api_verification_summary():
    from dalili.api import verification_summary

    out = verification_summary(days=365)
    return {k: out[k] for k in ("total", "verified_rate") if k in out}


def _verification_stats():
    from dalili.verification import verification_stats

    out = verification_stats(days=365)
    return {"total": out["total"], "verified_rate": out["verified_rate"],
            "groups": len(out["by_outcome"])}


def _conversion_stats():
    from dalili.integration import conversion_stats

    return conversion_stats()


def _prospect_form_data():
    from dalili.dalili.doctype.dalili_prospect.dalili_prospect import DaliliProspect  # noqa: F401

    doc = frappe.get_doc("Dalili Prospect", _first_prospect())
    breakdown = doc.get("score_breakdown") or ""
    return {"name": doc.name, "score": doc.get("total_score"),
            "has_breakdown": bool(breakdown)}


def _report_verification_funnel():
    from frappe.desk.query_report import run

    out = run("Dalili Verification Funnel") or {}
    return f"{len(out.get('result') or [])} rows, {len(out.get('chart') or {})} chart keys"


def _report_icp_performance():
    from frappe.desk.query_report import run

    out = run("Dalili ICP Performance") or {}
    return f"{len(out.get('result') or [])} rows"


def _export_csv():
    from dalili.api import export_csv

    out = export_csv(_first_lead_list())
    return {"file": out.get("file_url") or out.get("file")}


# ---------------------------------------------------------------------------
def run_all() -> None:
    """Print a PASS/FAIL table and a summary. Returns None (bench prints it)."""
    RESULTS.clear()

    print("=" * 78)
    print("DALILI SMOKE TEST —", frappe.local.site)
    print("=" * 78)

    checks = [
        ("seed data present", _seed_data, False),
        ("roles created", _roles, False),
        ("settings readable", _settings, False),
        ("swahili parser (pure)", _parser, False),
        ("scoring (pure)", _scoring, False),
        ("api.stats", _api_stats, False),
        ("api.sectors", _api_sectors, False),
        ("api.signal_types", _api_signal_types, False),
        ("api.chat (parse only)", _api_chat, False),
        ("api.list_briefs", _api_list_briefs, False),
        ("api.get_run", _api_get_run, False),
        ("api.get_brief (text)", _api_get_brief, False),
        ("brief.build_text", _brief_text, False),
        ("brief.build_html", _brief_html, False),
        ("brief.build_csv", _brief_csv, False),
        ("api.verification_summary", _api_verification_summary, False),
        ("verification.verification_stats", _verification_stats, False),
        ("integration.conversion_stats", _conversion_stats, False),
        ("prospect doc + score breakdown", _prospect_form_data, False),
        ("report: Verification Funnel", _report_verification_funnel, False),
        ("report: ICP Performance", _report_icp_performance, False),
        ("api.export_csv", _export_csv, True),
    ]

    for label, fn, writes in checks:
        _check(label, fn, writes=writes)

    width = max(len(r[1]) for r in RESULTS)
    for status, label, detail in RESULTS:
        mark = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{mark}] {label:<{width}}  {detail}")

    passed = sum(1 for r in RESULTS if r[0] == "PASS")
    failed = len(RESULTS) - passed
    print("-" * 78)
    print(f"  {passed} passed, {failed} failed")
    if failed:
        print("\n  Paste the FAIL lines above and we fix all of them at once.")
    print("=" * 78)


def traceback_on() -> None:
    """Enable full tracebacks for the next run_all() (debugging)."""
    frappe.flags.dalili_smoke_traceback = True
    print("full tracebacks enabled for the next run_all()")

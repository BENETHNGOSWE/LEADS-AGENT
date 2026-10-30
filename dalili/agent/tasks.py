"""Background job entry points (queued with frappe.enqueue on the `long` queue)."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate


def run_agent(run_name: str) -> None:
    """Execute a pre-created Agent Run (created by api.enqueue_run)."""
    run = frappe.get_doc("Dalili Agent Run", run_name)
    from dalili.agent.orchestrator import execute

    try:
        execute(run.icp, triggered_by=run.triggered_by, existing_run=run_name)
    except Exception:
        # execute() already marks the run Failed and logs it; avoid a duplicate job failure
        frappe.log_error(title=f"Dalili run {run_name} failed", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# scheduled jobs (see hooks.scheduler_events)
# ---------------------------------------------------------------------------
def daily_refresh() -> None:
    """Flag stale records and queue recurring ICPs whose turn has come."""
    from dalili.verification import queue_stale_prospects

    try:
        stale = queue_stale_prospects()
        if stale:
            frappe.logger("dalili").info(f"Queued {stale} stale prospect(s) for re-verification")
    except Exception:
        frappe.log_error(title="Dalili: stale queue job failed", message=frappe.get_traceback())

    try:
        _run_recurring_icps()
    except Exception:
        frappe.log_error(title="Dalili: recurring ICP job failed", message=frappe.get_traceback())


def _run_recurring_icps() -> None:
    settings = frappe.get_cached_doc("Dalili Settings")
    if not settings.enabled:
        return

    icps = frappe.get_all(
        "Dalili ICP",
        filters={"status": "Active", "is_recurring": 1},
        fields=["name", "recurrence", "last_run_on"],
    )
    for icp in icps:
        interval = {"Weekly": 7, "Monthly": 30, "Quarterly": 90}.get(icp.recurrence or "", 30)
        due_on = add_days(icp.last_run_on.date() if icp.last_run_on else add_days(nowdate(), -interval), interval)
        if due_on > frappe.utils.getdate(nowdate()):
            continue
        frappe.enqueue(
            "dalili.agent.tasks.run_agent_for_icp",
            queue="long",
            timeout=3600,
            icp=icp.name,
        )


def run_agent_for_icp(icp: str) -> None:
    from dalili.agent.orchestrator import execute

    try:
        execute(icp, triggered_by="Administrator")
    except Exception:
        frappe.log_error(title=f"Dalili recurring run failed for {icp}", message=frappe.get_traceback())


def weekly_digest() -> None:
    """Email a short operational summary to the configured address."""
    settings = frappe.get_cached_doc("Dalili Settings")
    if not settings.notify_email:
        return
    try:
        from dalili.api import stats

        data = stats()
        message = (
            f"Prospects: {data['prospects']} · verified: {data['verified']} "
            f"({data['verified_rate']}%) · stale: {data['stale']}\n"
            f"Active ICPs: {data['icps']} · runs: {data['runs']} · lists: {data['lead_lists']}\n"
            f"Verification (90d): {data['verification']['answered']} answered of "
            f"{data['verification']['total']} attempts\n"
            f"Converted to leads: {data['conversions']['converted']} "
            f"({data['conversions']['conversion_rate']}%)\n"
        )
        frappe.sendmail(
            recipients=[settings.notify_email],
            subject="Dalili weekly digest",
            message=message,
            now=True,
        )
    except Exception:
        frappe.log_error(title="Dalili: weekly digest failed", message=frappe.get_traceback())

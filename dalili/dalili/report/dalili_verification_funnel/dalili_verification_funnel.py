"""Verification Funnel.

The number this report exists to produce is the *verified rate*: of every contact
we handed a customer, how many actually answered? That single metric is the promise
the business sells ("replace-or-refund"), so it must be visible and unflattering.
"""

import frappe
from frappe import _
from frappe.utils import add_days, nowdate

GOOD = ("Answered - verified",)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    from_date = filters.get("from_date") or add_days(nowdate(), -90)
    to_date = filters.get("to_date") or nowdate()

    columns = [
        {"label": _("Outcome"), "fieldname": "outcome", "fieldtype": "Data", "width": 220},
        {"label": _("Attempts"), "fieldname": "attempts", "fieldtype": "Int", "width": 120},
        {"label": _("Share %"), "fieldname": "share", "fieldtype": "Percent", "width": 110},
        {"label": _("Replacements issued"), "fieldname": "replacements", "fieldtype": "Int",
         "width": 170},
    ]

    rows = frappe.db.sql(
        """
        SELECT outcome,
               COUNT(name) AS attempts,
               SUM(CASE WHEN replacement_issued = 1 THEN 1 ELSE 0 END) AS replacements
        FROM `tabDalili Verification`
        WHERE DATE(verified_on) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY outcome
        ORDER BY attempts DESC
        """,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )

    total = sum(row.attempts or 0 for row in rows) or 1
    for row in rows:
        row.share = round(100.0 * (row.attempts or 0) / total, 1)

    answered = sum(row.attempts or 0 for row in rows if row.outcome in GOOD)
    bad = sum(
        row.attempts or 0
        for row in rows
        if row.outcome in ("Wrong person", "Left company", "Disconnected", "Wrong number")
    )

    report_summary = [
        {
            "label": _("Verified rate"),
            "value": f"{round(100.0 * answered / total, 1)}%",
            "indicator": "Green" if answered / total >= 0.8 else "Orange" if answered / total >= 0.6 else "Red",
            "datatype": "Data",
        },
        {"label": _("Attempts"), "value": total - 1 if total == 1 and not rows else total,
         "datatype": "Int"},
        {
            "label": _("Bad leads"),
            "value": bad,
            "indicator": "Red" if bad else "Green",
            "datatype": "Int",
        },
        {
            "label": _("Replacements issued"),
            "value": sum(row.replacements or 0 for row in rows),
            "datatype": "Int",
        },
    ]

    chart = {
        "data": {
            "labels": [row.outcome for row in rows],
            "datasets": [{"name": _("Attempts"), "values": [row.attempts for row in rows]}],
        },
        "type": "donut",
        "height": 280,
    }

    return columns, rows, None, chart, report_summary

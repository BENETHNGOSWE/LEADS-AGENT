"""ICP Performance.

Answers the only question a paying customer asks after month two: is the list
actually turning into pipeline? Leads delivered, average score, how many were
converted into ERPNext leads, and how many contacts were verified.
"""

import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})

    conditions = ""
    values = {}
    if filters.get("status"):
        conditions = "WHERE icp.status = %(status)s"
        values["status"] = filters.status

    columns = [
        {"label": _("ICP"), "fieldname": "icp_name", "fieldtype": "Link",
         "options": "Dalili ICP", "width": 240},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
        {"label": _("Sector"), "fieldname": "sector", "fieldtype": "Link",
         "options": "Dalili Sector", "width": 170},
        {"label": _("Region"), "fieldname": "region", "fieldtype": "Data", "width": 130},
        {"label": _("Runs"), "fieldname": "runs", "fieldtype": "Int", "width": 80},
        {"label": _("Last run"), "fieldname": "last_run_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Leads delivered"), "fieldname": "leads_delivered", "fieldtype": "Int",
         "width": 130},
        {"label": _("Avg score"), "fieldname": "avg_score", "fieldtype": "Float", "width": 100},
        {"label": _("Converted"), "fieldname": "converted", "fieldtype": "Int", "width": 110},
        {"label": _("Conversion %"), "fieldname": "conversion_rate", "fieldtype": "Percent",
         "width": 120},
    ]

    data = frappe.db.sql(
        f"""
        SELECT
            icp.name           AS icp,
            icp.icp_name       AS icp_name,
            icp.status         AS status,
            icp.sector         AS sector,
            icp.region         AS region,
            icp.last_run_on    AS last_run_on,
            (SELECT COUNT(name) FROM `tabDalili Agent Run` r WHERE r.icp = icp.name) AS runs,
            COALESCE(SUM(ll.total_prospects), 0) AS leads_delivered,
            COALESCE(ROUND(AVG(NULLIF(ll.avg_score, 0)), 1), 0) AS avg_score,
            (
                SELECT COUNT(p.name)
                FROM `tabDalili Prospect` p
                JOIN `tabDalili Lead List Item` li ON li.prospect = p.name
                JOIN `tabDalili Lead List` l2 ON l2.name = li.parent
                WHERE l2.icp = icp.name AND p.status = 'Converted'
            ) AS converted
        FROM `tabDalili ICP` icp
        LEFT JOIN `tabDalili Lead List` ll ON ll.icp = icp.name
        {conditions}
        GROUP BY icp.name
        ORDER BY leads_delivered DESC
        """,
        values,
        as_dict=True,
    )

    for row in data:
        delivered = row.leads_delivered or 0
        row.conversion_rate = round(100.0 * (row.converted or 0) / delivered, 1) if delivered else 0

    total_leads = sum(row.leads_delivered or 0 for row in data)
    total_converted = sum(row.converted or 0 for row in data)
    report_summary = [
        {"label": _("Active ICPs"), "value": sum(1 for r in data if r.status == "Active"),
         "datatype": "Int"},
        {"label": _("Leads delivered"), "value": total_leads, "datatype": "Int"},
        {"label": _("Converted"), "value": total_converted, "datatype": "Int"},
        {
            "label": _("Conversion %"),
            "value": round(100.0 * total_converted / total_leads, 1) if total_leads else 0,
            "datatype": "Percent",
            "indicator": "Green" if total_leads and total_converted / total_leads >= 0.15 else "Orange",
        },
    ]

    chart = {
        "data": {
            "labels": [row.icp_name for row in data][:10],
            "datasets": [
                {"name": _("Leads delivered"), "values": [row.leads_delivered for row in data][:10]},
                {"name": _("Converted"), "values": [row.converted for row in data][:10]},
            ],
        },
        "type": "bar",
        "height": 300,
    }

    return columns, data, None, chart, report_summary

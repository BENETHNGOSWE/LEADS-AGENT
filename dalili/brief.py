"""Delivery: the brief the customer actually reads.

The product is not a dashboard. In Tanzania the brief arrives on WhatsApp (or as a
one-page PDF), in Swahili or English, and it is short enough to act on in the car.
This module renders the same lead list three ways: plain text for WhatsApp, HTML
for print/PDF, and CSV for a CRM.
"""

from __future__ import annotations

import csv
import io

import frappe
from frappe.utils import formatdate

from dalili.logic.normalize import whatsapp_link

MAX_TEXT_ITEMS = 25


def _settings():
    return frappe.get_cached_doc("Dalili Settings")


def _score_label(score) -> str:
    try:
        score = float(score or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 80:
        return "HOT"
    if score >= 65:
        return "WARM"
    return "COOL"


def build_text(lead_list_name: str, *, limit: int = MAX_TEXT_ITEMS) -> str:
    """WhatsApp-ready plain text brief (no markdown that WhatsApp will mangle)."""
    lead_list = frappe.get_doc("Dalili Lead List", lead_list_name)
    settings = _settings()
    icp = frappe.get_doc("Dalili ICP", lead_list.icp) if lead_list.icp else None
    items = [row for row in lead_list.items if row.included][:limit]

    lines = [
        f"*DALILI BRIEF — {formatdate(lead_list.generated_on or frappe.utils.nowdate())}*",
        f"{icp.icp_name if icp else lead_list.list_name}",
        f"{len(items)} leads · avg score {round(lead_list.avg_score or 0)} · "
        f"verified {lead_list.verified_count or 0}/{lead_list.total_prospects or 0}",
        "",
    ]

    for row in items:
        prospect = frappe.db.get_value(
            "Dalili Prospect",
            row.prospect,
            ["company_name", "region", "district", "employee_band", "primary_phone"],
            as_dict=True,
        ) or {}
        lines.append(
            f"{row.rank}. *{row.company_name or prospect.get('company_name') or row.prospect}* "
            f"[{_score_label(row.score)} {round(row.score or 0)}]"
        )
        location = ", ".join(x for x in [prospect.get("district"), prospect.get("region")] if x)
        if location or prospect.get("employee_band"):
            lines.append(
                f"   {location}"
                + (f" · {prospect.get('employee_band')} staff" if prospect.get("employee_band") else "")
            )
        if row.contact_name:
            role = frappe.db.get_value("Dalili Contact", row.contact, "role_title") if row.contact else ""
            lines.append(f"   👤 {row.contact_name}" + (f" — {role}" if role else ""))
        if row.whatsapp or row.phone:
            lines.append(f"   📱 {row.whatsapp or row.phone}" +
                         (" (WhatsApp)" if row.whatsapp else ""))
        if row.why_now:
            lines.append(f"   ⚡ {row.why_now}")
        if row.phone:
            link = whatsapp_link(row.whatsapp or row.phone, _opener(lead_list, row))
            if link:
                lines.append(f"   🔗 {link}")
        lines.append("")

    if settings.brief_signature:
        lines.append(f"— {settings.brief_signature}")
    if settings.replace_bad_leads:
        lines.append("Wrong number? Reply BAD <n> and we replace it free.")
    return "\n".join(lines).strip()


def _opener(lead_list, row) -> str:
    """A first-message suggestion in the ICP's language."""
    icp = frappe.get_doc("Dalili ICP", lead_list.icp) if lead_list.icp else None
    language = (icp.languages if icp else "Both") or "Both"
    name = (row.contact_name or "").split(" ")[0] or "Habari"
    if language == "Swahili":
        return (
            f"Habari {name}, nina wasiliana kuhusu {icp.sector or 'huduma zetu'}. "
            f"Tunaweza kupanga mazungumzo ya dakika 10 wiki hii?"
        )
    return (
        f"Hi {name}, I'm reaching out about {icp.sector or 'our services'}. "
        f"Could we book 10 minutes this week?"
    )


def build_html(lead_list_name: str) -> str:
    """Printable one-pager (also used by the 'Lead Brief' print format)."""
    lead_list = frappe.get_doc("Dalili Lead List", lead_list_name)
    items = [row for row in lead_list.items if row.included]
    icp = frappe.get_doc("Dalili ICP", lead_list.icp) if lead_list.icp else None

    rows = []
    for row in items:
        prospect = frappe.db.get_value(
            "Dalili Prospect", row.prospect,
            ["region", "district", "employee_band", "verification_status", "last_verified_on"],
            as_dict=True,
        ) or {}
        rows.append(
            f"""<tr>
  <td class="rank">{row.rank}</td>
  <td>
    <strong>{frappe.utils.escape_html(row.company_name or row.prospect)}</strong>
    <div class="muted">{frappe.utils.escape_html(', '.join(
        x for x in [prospect.get('district'), prospect.get('region')] if x))}
      {' · ' + frappe.utils.escape_html(prospect.get('employee_band') or '') if prospect.get('employee_band') else ''}
    </div>
    <div class="why">{frappe.utils.escape_html(row.why_now or '')}</div>
  </td>
  <td>
    <div>{frappe.utils.escape_html(row.contact_name or '—')}</div>
    <div class="muted">{frappe.utils.escape_html(row.whatsapp or row.phone or '')}</div>
  </td>
  <td class="score {'hot' if (row.score or 0) >= 80 else 'warm' if (row.score or 0) >= 65 else ''}">
    {round(row.score or 0)}
  </td>
  <td class="muted">{prospect.get('verification_status') or '—'}</td>
</tr>"""
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Dalili Brief — {frappe.utils.escape_html(lead_list.list_name)}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color:#111; margin:28px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .sub {{ color:#666; font-size:12px; margin-bottom:16px; }}
  .stats {{ display:flex; gap:22px; margin:14px 0 20px; font-size:12px; color:#444; }}
  .stats b {{ display:block; font-size:18px; color:#111; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th {{ text-align:left; border-bottom:2px solid #1f3b57; padding:8px 6px; color:#1f3b57; }}
  td {{ border-bottom:1px solid #e6e6e6; padding:9px 6px; vertical-align:top; }}
  .muted {{ color:#777; font-size:11px; }}
  .why {{ color:#0b6b3a; font-size:11px; margin-top:3px; }}
  .rank {{ color:#999; width:26px; }}
  .score {{ font-weight:700; text-align:right; }}
  .score.hot {{ color:#b3261e; }}
  .score.warm {{ color:#a06400; }}
  footer {{ margin-top:18px; font-size:10px; color:#888; border-top:1px solid #e6e6e6; padding-top:8px; }}
</style></head>
<body>
  <h1>Dalili Lead Brief</h1>
  <div class="sub">{frappe.utils.escape_html(lead_list.list_name)}
    {(' · ' + frappe.utils.escape_html(icp.icp_name)) if icp else ''}</div>
  <div class="stats">
    <div><b>{lead_list.total_prospects or 0}</b>prospects</div>
    <div><b>{lead_list.total_contacts or 0}</b>contacts</div>
    <div><b>{lead_list.verified_count or 0}</b>verified</div>
    <div><b>{round(lead_list.avg_score or 0)}</b>avg score</div>
  </div>
  <table>
    <thead><tr>
      <th>#</th><th>Company / why now</th><th>Contact</th><th>Score</th><th>Verified</th>
    </tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="5">No leads in this list.</td></tr>'}</tbody>
  </table>
  <footer>{frappe.utils.escape_html(_settings().brief_signature or '')}
    · generated {formatdate(lead_list.generated_on or frappe.utils.nowdate())}</footer>
</body></html>"""


def build_csv(lead_list_name: str) -> str:
    """CSV for the customer's CRM. One row per lead, contact columns flattened."""
    lead_list = frappe.get_doc("Dalili Lead List", lead_list_name)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "rank", "company", "score", "sector", "region", "district", "employee_band",
        "contact_name", "role", "phone", "whatsapp", "email", "verified_on",
        "verification_status", "why_now", "whatsapp_link", "prospect",
    ])
    for row in lead_list.items:
        if not row.included:
            continue
        prospect = frappe.db.get_value(
            "Dalili Prospect", row.prospect,
            ["company_name", "sector", "region", "district", "employee_band",
             "verification_status", "last_verified_on"],
            as_dict=True,
        ) or {}
        contact = frappe.db.get_value(
            "Dalili Contact", row.contact, ["role_title", "email"], as_dict=True
        ) if row.contact else {}
        writer.writerow([
            row.rank, row.company_name or prospect.get("company_name"), round(row.score or 0),
            prospect.get("sector"), prospect.get("region"), prospect.get("district"),
            prospect.get("employee_band"), row.contact_name, (contact or {}).get("role_title"),
            row.phone, row.whatsapp, (contact or {}).get("email"),
            prospect.get("last_verified_on"), prospect.get("verification_status"),
            row.why_now, whatsapp_link(row.whatsapp or row.phone or ""), row.prospect,
        ])
    return buffer.getvalue()

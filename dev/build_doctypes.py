"""
Dev tool: generates the DocType JSON definitions for the `dalili` Frappe app.

Run from the repo root:  python3 dev/build_doctypes.py
It writes dalili/dalili/doctype/<doctype>/<doctype>.json (+ __init__.py placeholders).
The generated JSON is what ships with the app; this script exists so the schema
stays consistent and is easy to extend.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCTYPE_DIR = ROOT / "dalili" / "dalili" / "doctype"
MODIFIED = "2026-10-30 09:00:00.000000"

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def f(fieldname, label, fieldtype, options=None, **kw):
    d = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}
    if options is not None:
        d["options"] = options
    d.update(kw)
    if fieldtype == "Section Break":
        d.setdefault("collapsible", 0)
    return d


def perms(table=False):
    if table:
        return [
            {"read": 1, "role": "System Manager"},
            {"read": 1, "role": "Dalili Manager"},
            {"read": 1, "role": "Dalili Agent"},
            {"read": 1, "role": "Sales User"},
        ]
    return [
        {
            "role": "System Manager",
            "read": 1, "write": 1, "create": 1, "delete": 1,
            "report": 1, "export": 1, "print": 1, "email": 1, "share": 1,
        },
        {
            "role": "Dalili Manager",
            "read": 1, "write": 1, "create": 1, "delete": 0,
            "report": 1, "export": 1, "print": 1, "email": 1, "share": 1,
        },
        {
            "role": "Dalili Agent",
            "read": 1, "write": 1, "create": 1, "delete": 0,
            "report": 1, "export": 1, "print": 1, "email": 0, "share": 0,
        },
        {
            "role": "Sales User",
            "read": 1, "write": 0, "create": 0, "delete": 0,
            "report": 1, "export": 1, "print": 1, "email": 0, "share": 1,
        },
    ]


def doctype(name, fields, *, autoname=None, naming_series=None, single=False,
            istable=False, title_field=None, search_fields=None,
            quick_entry=0, track_changes=1, description=None, sort_field="modified",
            permissions=None, default_print_format=None):
    fieldnames = [x["fieldname"] for x in fields]
    doc = {
        "actions": [],
        "allow_rename": 1 if (title_field and not naming_series) else 0,
        "creation": MODIFIED,
        "doctype": "DocType",
        "editable_grid": 1,
        "engine": "InnoDB",
        "field_order": fieldnames,
        "fields": fields,
        "index_web_pages_for_search": 0 if istable else 1,
        "links": [],
        "modified": MODIFIED,
        "modified_by": "Administrator",
        "module": "Dalili",
        "name": name,
        "owner": "Administrator",
        "permissions": permissions if permissions is not None else perms(table=istable),
        "sort_field": sort_field,
        "sort_order": "DESC",
        "states": [],
        "track_changes": track_changes,
    }
    if single:
        doc["issingle"] = 1
        doc.pop("allow_rename", None)
    if istable:
        doc["istable"] = 1
    if autoname:
        doc["autoname"] = autoname
    if naming_series:
        doc["autoname"] = "naming_series:"
        doc["naming_series"] = naming_series
    if title_field:
        doc["title_field"] = title_field
    if search_fields:
        doc["search_fields"] = search_fields
    if quick_entry:
        doc["quick_entry"] = 1
    if description:
        doc["description"] = description
    if default_print_format:
        doc["default_print_format"] = default_print_format
    return doc


DOCTYPE_DEFS = []


def add(doc):
    DOCTYPE_DEFS.append(doc)


# --------------------------------------------------------------------------
# 1. Dalili Settings (Single)
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Settings",
    [
        f("enabled", "Enabled", "Check", default="1"),
        f("demo_mode", "Demo Mode (no external API calls)", "Check", default="1"),
        f("sb_market", "Market Defaults", "Section Break"),
        f("default_country", "Default Country", "Data", "Tanzania", default="Tanzania"),
        f("default_region", "Default Region", "Data", default="Dar es Salaam"),
        f("phone_country_code", "Phone Country Code", "Data", default="255"),
        f("default_language", "Default Language", "Select", "Swahili\nEnglish\nBoth", default="Swahili"),
        f("cb_market", "", "Column Break"),
        f("default_currency", "Default Currency", "Link", "Currency", default="TZS"),
        f("max_leads_per_list", "Max Leads per List", "Int", default="200"),
        f("default_target_count", "Default Target Count", "Int", default="50"),
        f("sb_verification", "Verification Policy", "Section Break"),
        f("verification_sla_days", "Verification SLA (days)", "Int", default="30",
          description="A record older than this is considered stale and is re-queued."),
        f("replace_bad_leads", "Replace Bad Leads Free", "Check", default="1"),
        f("max_replacements_per_month", "Max Replacements / Month", "Int", default="20"),
        f("auto_requeue_stale", "Auto Re-queue Stale Prospects", "Check", default="1"),
        f("cb_verification", "", "Column Break"),
        f("queue_stale_after_days", "Queue Stale After (days)", "Int", default="30"),
        f("require_consent_note", "Require Consent Basis on Contacts", "Check", default="1"),
        f("sb_scoring", "Scoring Weights", "Section Break",
          description="Weights are normalised to 100 when scoring a prospect."),
        f("weight_fit", "Fit Weight", "Float", default="35"),
        f("weight_signal", "Signal Weight", "Float", default="30"),
        f("weight_confidence", "Data Confidence Weight", "Float", default="20"),
        f("weight_contactability", "Contactability Weight", "Float", default="15"),
        f("cb_scoring", "", "Column Break"),
        f("min_score_default", "Default Minimum Score", "Int", default="60"),
        f("signal_decay_days", "Signal Decay (days)", "Int", default="90"),
        f("sb_llm", "AI / LLM", "Section Break"),
        f("llm_enabled", "LLM Enabled", "Check", default="0"),
        f("llm_model", "LLM Model", "Data", default="gpt-4o-mini"),
        f("llm_base_url", "LLM Base URL", "Data", default="https://api.openai.com/v1"),
        f("llm_api_key", "LLM API Key", "Password"),
        f("cb_llm", "", "Column Break"),
        f("llm_timeout", "LLM Timeout (seconds)", "Int", default="30"),
        f("llm_max_tokens", "LLM Max Tokens", "Int", default="700"),
        f("sb_delivery", "Delivery", "Section Break"),
        f("brief_signature", "Brief Signature", "Small Text",
          default="Dalili Lead Engine — verified leads for Tanzanian B2B teams"),
        f("notify_email", "Notify Email", "Data"),
        f("whatsapp_sender", "WhatsApp Sender", "Data"),
        f("enable_portal", "Enable Portal Page (/dalili)", "Check", default="1"),
    ],
    single=True,
    autoname=None,
    description="Global configuration for the Dalili lead engine.",
))

# --------------------------------------------------------------------------
# 2. Dalili Sector
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Sector",
    [
        f("sector_name", "Sector Name", "Data", reqd=1, unique=1, in_list_view=1),
        f("sector_group", "Sector Group", "Select",
          "Agriculture\nManufacturing\nTrade & Retail\nServices\nHospitality & Tourism\n"
          "Health\nEducation\nConstruction & Real Estate\nTransport & Logistics\n"
          "Energy & Utilities\nICT & Media\nFinancial Services\nPublic Sector\nOther",
          in_list_view=1),
        f("cb1", "", "Column Break"),
        f("is_active", "Active", "Check", default="1", in_list_view=1),
        f("typical_size", "Typical Employee Band", "Select", "1-10\n11-50\n51-200\n200+"),
        f("sb1", "Matching", "Section Break"),
        f("keywords", "Matching Keywords", "Small Text",
          description="Comma separated keywords used to classify a company into this sector."),
        f("google_place_types", "Google Place Types", "Small Text",
          description="Comma separated Google Places types, e.g. lodging, restaurant, hospital."),
        f("exclude_keywords", "Exclusion Keywords", "Small Text"),
        f("sb2", "Notes", "Section Break"),
        f("signals_to_watch", "Signals to Watch", "Small Text",
          description="Signal types that usually precede a buying decision in this sector."),
        f("description", "Description", "Text"),
    ],
    autoname="field:sector_name",
    title_field="sector_name",
    search_fields="sector_name,sector_group",
    quick_entry=1,
))

# --------------------------------------------------------------------------
# 3. Dalili Signal Type
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Signal Type",
    [
        f("signal_name", "Signal Name", "Data", reqd=1, unique=1, in_list_view=1),
        f("category", "Category", "Select",
          "Registration\nLicence\nTender Award\nTender Publish\nHiring\nShipment / Import\n"
          "Expansion\nFunding\nLeadership Change\nSocial Activity\nWebsite Change\nOther",
          in_list_view=1, reqd=1),
        f("cb1", "", "Column Break"),
        f("weight", "Weight", "Float", default="10", in_list_view=1,
          description="Base strength of this signal type (0-20). Scaled into the signal score."),
        f("decay_days", "Decay (days)", "Int", default="90"),
        f("is_active", "Active", "Check", default="1", in_list_view=1),
        f("sb1", "Sourcing", "Section Break"),
        f("source", "Typical Source", "Link", "Dalili Data Source"),
        f("description", "Description", "Small Text"),
        f("detection_hint", "Detection Hint", "Small Text",
          description="How the agent should look for this signal."),
    ],
    autoname="field:signal_name",
    title_field="signal_name",
    search_fields="signal_name,category",
    quick_entry=1,
))

# --------------------------------------------------------------------------
# 4. Dalili Data Source
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Data Source",
    [
        f("source_name", "Source Name", "Data", reqd=1, unique=1, in_list_view=1),
        f("source_type", "Source Type", "Select",
          "Places API\nCompany Registry\nWebsite\nSocial Profile\nTrade Data\nJob Board\n"
          "Tender Portal\nLicensing Authority\nCredit Bureau\nLLM Research\nCSV Upload\nManual",
          reqd=1, in_list_view=1),
        f("cb1", "", "Column Break"),
        f("enabled", "Enabled", "Check", default="1", in_list_view=1),
        f("priority", "Waterfall Priority", "Int", default="10", in_list_view=1,
          description="Lower runs first in the enrichment waterfall."),
        f("reliability", "Reliability %", "Percent", default="70",
          description="Used as the source confidence weight when merging records."),
        f("sb1", "Access", "Section Break"),
        f("endpoint", "Endpoint", "Data"),
        f("api_key", "API Key", "Password"),
        f("rate_limit_per_min", "Rate Limit / min", "Int", default="60"),
        f("cost_per_call", "Cost per Call", "Float", default="0",
          description="Used for agent run cost estimates."),
        f("cb2", "", "Column Break"),
        f("last_success_on", "Last Success On", "Datetime", read_only=1),
        f("last_error", "Last Error", "Small Text", read_only=1),
        f("sb2", "Notes", "Section Break"),
        f("notes", "Notes", "Small Text"),
    ],
    autoname="field:source_name",
    title_field="source_name",
    search_fields="source_name,source_type",
    quick_entry=1,
))

# --------------------------------------------------------------------------
# 5. Dalili ICP
# --------------------------------------------------------------------------
add(doctype(
    "Dalili ICP",
    [
        f("naming_series", "Series", "Select", "ICP-.YYYY.-.#####", default="ICP-.YYYY.-.#####",
          hidden=1),
        f("icp_name", "ICP Name", "Data", reqd=1, in_list_view=1),
        f("owner_user", "Assigned To", "Link", "User", in_list_view=1,
          default="__user"),
        f("cb1", "", "Column Break"),
        f("status", "Status", "Select", "Draft\nActive\nPaused\nArchived", default="Active",
          in_list_view=1),
        f("is_recurring", "Recurring", "Check", in_list_view=1),
        f("recurrence", "Recurrence", "Select", "Weekly\nMonthly\nQuarterly"),
        f("sb_prompt", "Natural Language Brief", "Section Break",
          description="What the customer typed. Kept for the audit trail and for re-parsing."),
        f("prompt_text", "Prompt", "Long Text"),
        f("sb_filters", "Target Filters", "Section Break"),
        f("sector", "Sector", "Link", "Dalili Sector", in_list_view=1),
        f("cb2", "", "Column Break"),
        f("region", "Region", "Data", default="Dar es Salaam",
          description="Region or city. Blank means anywhere in the country."),
        f("district", "District / Ward", "Data"),
        f("sb_size", "Company Size", "Section Break"),
        f("employee_band_min", "Employees (min)", "Int"),
        f("employee_band_max", "Employees (max)", "Int"),
        f("cb3", "", "Column Break"),
        f("revenue_band", "Revenue Band", "Select",
          "\nBelow TZS 50M\nTZS 50M - 200M\nTZS 200M - 1B\nAbove TZS 1B"),
        f("founded_after", "Founded After", "Int"),
        f("sb_keywords", "Keywords", "Section Break"),
        f("include_keywords", "Must Contain", "Small Text",
          description="Comma separated. Company name, product or description must match one of these."),
        f("exclude_keywords", "Must Not Contain", "Small Text",
          description="Hard exclusion. Matching companies are dropped before scoring."),
        f("cb4", "", "Column Break"),
        f("languages", "Outreach Language", "Select", "Swahili\nEnglish\nBoth", default="Both"),
        f("seniority_preference", "Contact Seniority", "Select",
          "Any\nOwner / Founder\nC-Level\nDirector\nManager\nOfficer", default="Any"),
        f("sb_signals", "Buying Signals", "Section Break"),
        f("watch_signals", "Signals to Watch", "Table MultiSelect", "Dalili ICP Signal",
          description="Leave empty to watch every active signal type."),
        f("min_signal_strength", "Minimum Signal Strength", "Float", default="0"),
        f("sb_delivery", "Output", "Section Break"),
        f("target_count", "Leads per Run", "Int", default="50"),
        f("min_score", "Minimum Score", "Int", default="60"),
        f("cb5", "", "Column Break"),
        f("delivery_channel", "Delivery Channel", "Select", "Desk\nWhatsApp\nEmail", default="Desk"),
        f("delivery_to", "Deliver To", "Data"),
        f("sb_meta", "Meta", "Section Break"),
        f("last_run_on", "Last Run On", "Datetime", read_only=1),
        f("total_leads_delivered", "Total Leads Delivered", "Int", read_only=1),
        f("notes", "Notes", "Small Text"),
    ],
    naming_series="ICP-.YYYY.-.#####",
    title_field="icp_name",
    search_fields="icp_name,sector,region",
    quick_entry=1,
))

# --------------------------------------------------------------------------
# 6. Dalili ICP Signal (table multi-select)
# --------------------------------------------------------------------------
add(doctype(
    "Dalili ICP Signal",
    [
        f("signal_type", "Signal Type", "Link", "Dalili Signal Type", reqd=1, in_list_view=1),
    ],
    istable=True,
))

# --------------------------------------------------------------------------
# 7. Dalili Prospect
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Prospect",
    [
        f("naming_series", "Series", "Select", "PROS-.#####", default="PROS-.#####", hidden=1),
        f("company_name", "Company Name", "Data", reqd=1, in_list_view=1),
        f("normalized_key", "Match Key", "Data", unique=1, no_copy=1,
          description="Deterministic entity-resolution key. Auto-generated."),
        f("cb1", "", "Column Break"),
        f("status", "Status", "Select",
          "New\nEnriched\nScored\nVerified\nQualified\nConverted\nDisqualified\nSuppressed\nArchived",
          default="New", in_list_view=1, no_copy=1),
        f("is_demo", "Demo Record", "Check", read_only=1, no_copy=1),
        f("sb_identity", "Identity", "Section Break"),
        f("legal_name", "Legal Name", "Data"),
        f("sector", "Sector", "Link", "Dalili Sector", in_list_view=1),
        f("sub_sector", "Sub Sector", "Data"),
        f("cb2", "", "Column Break"),
        f("brela_number", "BRELA Number", "Data"),
        f("tin", "TIN", "Data"),
        f("vat_number", "VAT Number", "Data"),
        f("sb_location", "Location", "Section Break"),
        f("region", "Region", "Data", in_list_view=1),
        f("district", "District", "Data"),
        f("ward", "Ward", "Data"),
        f("cb3", "", "Column Break"),
        f("address", "Address", "Small Text"),
        f("latitude", "Latitude", "Float", precision="6"),
        f("longitude", "Longitude", "Float", precision="6"),
        f("sb_contact", "Primary Contact Points", "Section Break"),
        f("primary_phone", "Primary Phone", "Data", in_list_view=1),
        f("primary_whatsapp", "Primary WhatsApp", "Data"),
        f("primary_email", "Primary Email", "Data"),
        f("cb4", "", "Column Break"),
        f("website", "Website", "Data"),
        f("domain", "Domain", "Data"),
        f("employee_band", "Employee Band", "Select", "1-10\n11-50\n51-200\n200+"),
        f("revenue_band", "Revenue Band", "Select",
          "\nBelow TZS 50M\nTZS 50M - 200M\nTZS 200M - 1B\nAbove TZS 1B"),
        f("founded_year", "Founded Year", "Int"),
        f("sb_scores", "Scores", "Section Break"),
        f("total_score", "Total Score", "Float", in_list_view=1, read_only=1),
        f("fit_score", "Fit", "Float", read_only=1),
        f("signal_score", "Signal", "Float", read_only=1),
        f("confidence_score", "Confidence", "Float", read_only=1),
        f("contactability_score", "Contactability", "Float", read_only=1),
        f("cb5", "", "Column Break"),
        f("verified_contacts", "Verified Contacts", "Int", read_only=1),
        f("signal_count", "Signals", "Int", read_only=1),
        f("score_breakdown", "Score Breakdown (JSON)", "Code", options="JSON",
          read_only=1, no_copy=1),
        f("sb_verification", "Verification", "Section Break"),
        f("verification_status", "Verification Status", "Select",
          "Unverified\nPartial\nVerified\nStale\nFailed", default="Unverified",
          in_list_view=1, read_only=1),
        f("last_verified_on", "Last Verified On", "Date", read_only=1),
        f("next_verification_on", "Next Verification On", "Date", read_only=1,
          in_list_view=1),
        f("cb6", "", "Column Break"),
        f("best_contact", "Best Contact", "Link", "Dalili Contact", read_only=1),
        f("suppressed", "Suppressed", "Check", read_only=1),
        f("suppression_reason", "Suppression Reason", "Small Text", read_only=1),
        f("sb_erpnext", "ERPNext Link", "Section Break"),
        f("lead_doctype", "Lead DocType", "Link", "DocType", read_only=1),
        f("erpnext_lead", "ERPNext Lead", "Dynamic Link", "lead_doctype", read_only=1),
        f("converted_on", "Converted On", "Datetime", read_only=1),
        f("sb_sources", "Source Trail", "Section Break"),
        f("sources", "Sources", "Table", "Dalili Source Ref"),
        f("sb_signals", "Buying Signals", "Section Break"),
        f("signals", "Signals", "Table", "Dalili Signal"),
        f("sb_notes", "Notes", "Section Break"),
        f("notes", "Notes", "Text"),
    ],
    naming_series="PROS-.#####",
    title_field="company_name",
    search_fields="company_name,primary_phone,region,domain,brela_number",
    quick_entry=1,
))

# --------------------------------------------------------------------------
# 8. Dalili Source Ref (child)
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Source Ref",
    [
        f("source", "Source", "Link", "Dalili Data Source", in_list_view=1),
        f("source_label", "Source Label", "Data", in_list_view=1),
        f("cb1", "", "Column Break"),
        f("source_type", "Type", "Data", in_list_view=1),
        f("confidence", "Confidence %", "Percent", in_list_view=1),
        f("cb2", "", "Column Break"),
        f("retrieved_on", "Retrieved On", "Datetime"),
        f("source_id", "Source Record ID", "Data"),
        f("url", "URL", "Data"),
        f("excerpt", "Excerpt", "Small Text"),
    ],
    istable=True,
))

# --------------------------------------------------------------------------
# 9. Dalili Signal (child)
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Signal",
    [
        f("signal_type", "Signal Type", "Link", "Dalili Signal Type", in_list_view=1, reqd=1),
        f("title", "Title", "Data", in_list_view=1, reqd=1),
        f("cb1", "", "Column Break"),
        f("category", "Category", "Data", in_list_view=1),
        f("detected_on", "Detected On", "Date", in_list_view=1),
        f("strength", "Strength", "Float", in_list_view=1),
        f("cb2", "", "Column Break"),
        f("evidence_url", "Evidence URL", "Data"),
        f("source", "Source", "Link", "Dalili Data Source"),
        f("why_now", "Why Now", "Small Text"),
    ],
    istable=True,
))

# --------------------------------------------------------------------------
# 10. Dalili Contact
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Contact",
    [
        f("naming_series", "Series", "Select", "CONT-.#####", default="CONT-.#####", hidden=1),
        f("prospect", "Prospect", "Link", "Dalili Prospect", reqd=1, in_list_view=1),
        f("full_name", "Full Name", "Data", in_list_view=1, reqd=1),
        f("cb1", "", "Column Break"),
        f("role_title", "Role / Title", "Data", in_list_view=1),
        f("department", "Department", "Select",
          "\nOwner / Founder\nExecutive\nProcurement\nFinance\nOperations\nSales\nIT\nHR\nOther"),
        f("seniority", "Seniority", "Select",
          "Owner / Founder\nC-Level\nDirector\nManager\nOfficer\nUnknown",
          default="Unknown", in_list_view=1),
        f("sb_contact", "Contact Points", "Section Break"),
        f("phone", "Phone", "Data", in_list_view=1),
        f("whatsapp", "WhatsApp", "Data"),
        f("email", "Email", "Data"),
        f("cb2", "", "Column Break"),
        f("linkedin_url", "LinkedIn", "Data"),
        f("language", "Language", "Select", "Swahili\nEnglish\nBoth", default="Swahili"),
        f("best_time_to_call", "Best Time to Call", "Data",
          description="e.g. Tue-Thu 09:00-11:00, learned from verification outcomes."),
        f("is_primary", "Primary Contact", "Check", in_list_view=1),
        f("sb_verification", "Verification", "Section Break"),
        f("verification_status", "Verification Status", "Select",
          "Unverified\nVerified\nWrong Person\nLeft Company\nDisconnected\nDo Not Contact\nStale",
          default="Unverified", in_list_view=1),
        f("verification_method", "Last Method", "Data", read_only=1),
        f("last_verified_on", "Last Verified On", "Date", read_only=1),
        f("next_check_on", "Next Check On", "Date", read_only=1),
        f("cb3", "", "Column Break"),
        f("confidence", "Confidence %", "Percent", default="50"),
        f("consent_basis", "Consent Basis", "Select",
          "Public business listing\nLegitimate B2B interest\nExplicit consent\nCustomer provided\nUnknown",
          default="Public business listing"),
        f("do_not_contact", "Do Not Contact", "Check", in_list_view=1),
        f("sb_source", "Source", "Section Break"),
        f("source", "Source", "Link", "Dalili Data Source"),
        f("source_url", "Source URL", "Data"),
        f("notes", "Notes", "Small Text"),
    ],
    naming_series="CONT-.#####",
    title_field="full_name",
    search_fields="full_name,phone,whatsapp,email,role_title",
    quick_entry=1,
))

# --------------------------------------------------------------------------
# 11. Dalili Agent Run
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Agent Run",
    [
        f("naming_series", "Series", "Select", "RUN-.YYYY.-.#####",
          default="RUN-.YYYY.-.#####", hidden=1),
        f("icp", "ICP", "Link", "Dalili ICP", reqd=1, in_list_view=1),
        f("status", "Status", "Select", "Queued\nRunning\nCompleted\nFailed\nCancelled",
          default="Queued", in_list_view=1, read_only=1),
        f("cb1", "", "Column Break"),
        f("started_at", "Started At", "Datetime", read_only=1),
        f("finished_at", "Finished At", "Datetime", read_only=1),
        f("duration_seconds", "Duration (s)", "Float", read_only=1),
        f("triggered_by", "Triggered By", "Link", "User", read_only=1),
        f("sb_counts", "Pipeline Counters", "Section Break"),
        f("discovered", "Discovered", "Int", read_only=1),
        f("duplicates_merged", "Duplicates Merged", "Int", read_only=1),
        f("enriched", "Enriched", "Int", read_only=1),
        f("scored", "Scored", "Int", read_only=1),
        f("qualified", "Qualified", "Int", read_only=1),
        f("delivered", "Delivered", "Int", read_only=1),
        f("cb2", "", "Column Break"),
        f("verification_required", "Needs Verification", "Int", read_only=1),
        f("cost_estimate", "Estimated Cost", "Currency", read_only=1),
        f("currency", "Currency", "Link", "Currency", read_only=1),
        f("lead_list", "Lead List", "Link", "Dalili Lead List", read_only=1),
        f("sb_log", "Log", "Section Break"),
        f("steps", "Steps", "Table", "Dalili Agent Step"),
        f("error_log", "Error", "Long Text", read_only=1),
        f("filters_snapshot", "Filters Snapshot (JSON)", "Code", options="JSON", read_only=1),
    ],
    naming_series="RUN-.YYYY.-.#####",
    title_field="icp",
    search_fields="icp,status",
))

# --------------------------------------------------------------------------
# 12. Dalili Agent Step (child)
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Agent Step",
    [
        f("sequence", "Seq", "Int", in_list_view=1),
        f("step_name", "Step", "Data", in_list_view=1, reqd=1),
        f("cb1", "", "Column Break"),
        f("status", "Status", "Select", "Pending\nRunning\nCompleted\nSkipped\nFailed",
          default="Pending", in_list_view=1),
        f("records_in", "In", "Int", in_list_view=1),
        f("records_out", "Out", "Int", in_list_view=1),
        f("cb2", "", "Column Break"),
        f("started_at", "Started", "Datetime"),
        f("finished_at", "Finished", "Datetime"),
        f("log", "Log", "Long Text"),
    ],
    istable=True,
))

# --------------------------------------------------------------------------
# 13. Dalili Lead List
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Lead List",
    [
        f("naming_series", "Series", "Select", "LIST-.YYYY.-.#####",
          default="LIST-.YYYY.-.#####", hidden=1),
        f("list_name", "List Name", "Data", reqd=1, in_list_view=1),
        f("icp", "ICP", "Link", "Dalili ICP", in_list_view=1),
        f("cb1", "", "Column Break"),
        f("status", "Status", "Select", "Draft\nReady\nDelivered\nExported\nArchived",
          default="Ready", in_list_view=1),
        f("generated_on", "Generated On", "Datetime", read_only=1, in_list_view=1),
        f("agent_run", "Agent Run", "Link", "Dalili Agent Run", read_only=1),
        f("sb_stats", "Stats", "Section Break"),
        f("total_prospects", "Prospects", "Int", read_only=1, in_list_view=1),
        f("total_contacts", "Contacts", "Int", read_only=1),
        f("verified_count", "Verified", "Int", read_only=1),
        f("cb2", "", "Column Break"),
        f("avg_score", "Average Score", "Float", read_only=1),
        f("delivered_on", "Delivered On", "Datetime", read_only=1),
        f("delivery_channel", "Delivered Via", "Data", read_only=1),
        f("delivered_to", "Delivered To", "Data", read_only=1),
        f("sb_items", "Leads", "Section Break"),
        f("items", "Items", "Table", "Dalili Lead List Item"),
        f("sb_meta", "Notes", "Section Break"),
        f("criteria_snapshot", "Criteria Snapshot (JSON)", "Code", options="JSON", read_only=1),
        f("notes", "Notes", "Small Text"),
    ],
    naming_series="LIST-.YYYY.-.#####",
    title_field="list_name",
    search_fields="list_name,icp,status",
))

# --------------------------------------------------------------------------
# 14. Dalili Lead List Item (child)
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Lead List Item",
    [
        f("prospect", "Prospect", "Link", "Dalili Prospect", reqd=1, in_list_view=1),
        f("company_name", "Company", "Data", in_list_view=1, read_only=1),
        f("rank", "Rank", "Int", in_list_view=1),
        f("cb1", "", "Column Break"),
        f("contact", "Contact", "Link", "Dalili Contact", in_list_view=1),
        f("contact_name", "Contact Name", "Data", read_only=1),
        f("phone", "Phone", "Data", read_only=1),
        f("whatsapp", "WhatsApp", "Data", read_only=1),
        f("score", "Score", "Float", in_list_view=1),
        f("cb2", "", "Column Break"),
        f("verified_on", "Verified On", "Date"),
        f("why_now", "Why Now", "Small Text", in_list_view=1),
        f("included", "Included", "Check", default="1", in_list_view=1),
        f("outcome", "Outcome", "Select",
          "\nNot contacted\nAnswered\nMeeting booked\nWrong person\nNot interested\nConverted"),
        f("outcome_on", "Outcome On", "Date"),
        f("outcome_notes", "Outcome Notes", "Small Text"),
    ],
    istable=True,
))

# --------------------------------------------------------------------------
# 15. Dalili Verification
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Verification",
    [
        f("naming_series", "Series", "Select", "VER-.YYYY.-.#####",
          default="VER-.YYYY.-.#####", hidden=1),
        f("prospect", "Prospect", "Link", "Dalili Prospect", reqd=1, in_list_view=1),
        f("contact", "Contact", "Link", "Dalili Contact", in_list_view=1),
        f("cb1", "", "Column Break"),
        f("method", "Method", "Select",
          "Outbound call\nSMS ping\nWhatsApp check\nWebsite check\nSwitchboard\nEmail check\nManual\nImported",
          reqd=1, in_list_view=1),
        f("outcome", "Outcome", "Select",
          "Answered - verified\nWrong person\nLeft company\nDisconnected\nNo answer\nDo not call\nWrong number",
          reqd=1, in_list_view=1),
        f("verified_on", "Verified On", "Datetime", in_list_view=1),
        f("cb2", "", "Column Break"),
        f("verified_by", "Verified By", "Link", "User"),
        f("cost", "Cost", "Float", default="0"),
        f("replacement_issued", "Replacement Issued", "Check", read_only=1),
        f("next_check_on", "Next Check On", "Date"),
        f("sb_detail", "Detail", "Section Break"),
        f("evidence", "Evidence / Notes", "Small Text"),
        f("learned_best_time", "Learned Best Time", "Data", read_only=1,
          description="Derived from answered outcomes for this contact."),
    ],
    naming_series="VER-.YYYY.-.#####",
    title_field="outcome",
    search_fields="prospect,contact,outcome,method",
))

# --------------------------------------------------------------------------
# 16. Dalili Suppression
# --------------------------------------------------------------------------
add(doctype(
    "Dalili Suppression",
    [
        f("naming_series", "Series", "Select", "SUP-.#####", default="SUP-.#####", hidden=1),
        f("suppression_type", "Type", "Select", "Phone\nEmail\nDomain\nCompany\nPerson",
          reqd=1, in_list_view=1),
        f("value", "Value", "Data", reqd=1, in_list_view=1,
          description="Normalised phone, lower-case email, domain, company name or person name."),
        f("cb1", "", "Column Break"),
        f("reason", "Reason", "Select",
          "Opt-out\nComplaint\nRegulatory\nManual\nBounced\nCustomer request", reqd=1,
          in_list_view=1),
        f("is_active", "Active", "Check", default="1", in_list_view=1),
        f("added_on", "Added On", "Datetime", read_only=1),
        f("added_by", "Added By", "Link", "User", read_only=1),
        f("sb1", "Context", "Section Break"),
        f("prospect", "Prospect", "Link", "Dalili Prospect"),
        f("contact", "Contact", "Link", "Dalili Contact"),
        f("source", "Source", "Data"),
        f("notes", "Notes", "Small Text"),
    ],
    naming_series="SUP-.#####",
    title_field="value",
    search_fields="value,suppression_type,reason",
))


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------
def main():
    DOCTYPE_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for doc in DOCTYPE_DEFS:
        folder = DOCTYPE_DIR / doc["name"].lower().replace(" ", "_")
        folder.mkdir(parents=True, exist_ok=True)
        init = folder / "__init__.py"
        if not init.exists():
            init.write_text("")
        target = folder / (folder.name + ".json")
        target.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        written += 1
    # package inits
    (DOCTYPE_DIR / "__init__.py").write_text("")
    print(f"wrote {written} doctypes to {DOCTYPE_DIR}")


if __name__ == "__main__":
    main()

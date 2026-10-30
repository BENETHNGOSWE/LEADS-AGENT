app_name = "dalili"
app_title = "Dalili Lead Engine"
app_publisher = "Dalili"
app_description = (
    "AI lead-generation agent for Tanzanian B2B sales teams: describe your ideal "
    "customer, get verified companies with decision-maker contacts and the reason "
    "to call them this week."
)
app_email = "hello@dalili.co.tz"
app_license = "mit"
app_version = "0.1.0"

# ERPNext is the platform; Dalili hands verified leads over to its CRM.
required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# install / upgrade
# ---------------------------------------------------------------------------
after_install = "dalili.install.after_install"
after_migrate = "dalili.install.after_migrate"

# ---------------------------------------------------------------------------
# integration with ERPNext's CRM
# ---------------------------------------------------------------------------
doc_events = {
    "Lead": {
        "on_update": "dalili.integration.on_lead_update",
    },
    "CRM Lead": {
        "on_update": "dalili.integration.on_lead_update",
    },
}

# ---------------------------------------------------------------------------
# scheduled work
# ---------------------------------------------------------------------------
scheduler_events = {
    "daily": [
        "dalili.agent.tasks.daily_refresh",
    ],
    "weekly": [
        "dalili.agent.tasks.weekly_digest",
    ],
}

# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
# No fixtures: reference data is created idempotently in dalili/install.py, which
# keeps `bench migrate` safe across schema changes.
fixtures = []

# Nothing is injected into every Desk page — Dalili stays out of the way until used.
# app_include_css = "/assets/dalili/css/dalili.css"

import frappe
from frappe.model.document import Document


class DaliliICP(Document):
    """A saved search — the customer's standing question: "who should we call?"

    Designed to be created from a sentence in Swahili or English (see
    dalili.logic.icp.parse_prompt) rather than from a 40-field form.
    """

    def validate(self):
        if not self.icp_name:
            self.icp_name = self.sector or "Untitled ICP"

        if self.target_count is None or int(self.target_count) <= 0:
            self.target_count = frappe.db.get_single_value("Dalili Settings", "default_target_count") or 50

        if not self.min_score:
            self.min_score = frappe.db.get_single_value("Dalili Settings", "min_score_default") or 60

        if (self.employee_band_min or 0) and (self.employee_band_max or 0) \
                and self.employee_band_min > self.employee_band_max:
            frappe.throw("Employees (min) cannot be greater than Employees (max)")

        if self.is_recurring and not self.recurrence:
            self.recurrence = "Weekly"

        if not self.owner_user:
            self.owner_user = frappe.session.user

    def before_insert(self):
        max_leads = frappe.db.get_single_value("Dalili Settings", "max_leads_per_list")
        if max_leads and (self.target_count or 0) > int(max_leads):
            self.target_count = int(max_leads)

    @frappe.whitelist(methods=["POST"])
    def run_now(self):
        from dalili.api import run_now

        return run_now(self.name)

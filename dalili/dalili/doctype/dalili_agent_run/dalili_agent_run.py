import frappe
from frappe.model.document import Document


class DaliliAgentRun(Document):
    """An audit trail of one agent execution.

    Kept read-only in the UI on purpose: a run is evidence of what the system did on
    the customer's behalf, not a document to be edited. Retries create a new run.
    """

    def validate(self):
        if self.status in ("Completed", "Failed", "Cancelled") and self.started_at \
                and self.finished_at and not self.duration_seconds:
            self.duration_seconds = frappe.utils.time_diff_in_seconds(
                self.finished_at, self.started_at
            )

    @frappe.whitelist(methods=["POST"])
    def retry(self):
        from dalili.api import enqueue_run

        return enqueue_run(self.icp)

    @frappe.whitelist(methods=["GET"])
    def open_brief(self):
        if not self.lead_list:
            frappe.throw("This run did not produce a lead list")
        return frappe.utils.get_url(f"/app/dalili-lead-list/{self.lead_list}")

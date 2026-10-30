import frappe
from frappe.model.document import Document


class DaliliLeadList(Document):
    """The deliverable: a ranked, verified shortlist the customer receives."""

    def validate(self):
        if not self.generated_on:
            self.generated_on = frappe.utils.now_datetime()

        rows = [row for row in (self.items or []) if row.included]
        scores = [float(row.score or 0) for row in rows]

        self.total_prospects = len(rows)
        self.total_contacts = sum(1 for row in rows if row.contact)
        self.verified_count = sum(1 for row in rows if row.verified_on)
        self.avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        # keep rank dense and ordered by score
        ordered = sorted(self.items or [], key=lambda r: float(r.score or 0), reverse=True)
        for index, row in enumerate(ordered, start=1):
            row.rank = index

    def before_save(self):
        if not self.list_name:
            self.list_name = f"Lead List {frappe.utils.formatdate(frappe.utils.nowdate())}"

    @frappe.whitelist(methods=["POST"])
    def mark_delivered(self, channel="WhatsApp", to=""):
        self.db_set(
            {
                "status": "Delivered",
                "delivery_channel": channel,
                "delivered_to": to,
                "delivered_on": frappe.utils.now_datetime(),
            }
        )
        return True

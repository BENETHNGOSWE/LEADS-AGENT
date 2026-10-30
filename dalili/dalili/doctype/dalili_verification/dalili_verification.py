import frappe
from frappe.model.document import Document

from dalili.logic.normalize import normalize_phone


class DaliliVerification(Document):
    """An audit record of one attempt to confirm a contact still exists.

    This table is the compounding asset: after thousands of rows, the product knows
    which numbers answer, when, and who picked up — evidence no competitor can buy.
    """

    def validate(self):
        if not self.prospect:
            frappe.throw("Prospect is required")
        if not self.outcome:
            frappe.throw("Outcome is required")
        if not self.verified_on:
            self.verified_on = frappe.utils.now_datetime()
        if not self.verified_by:
            self.verified_by = frappe.session.user

        if self.contact:
            contact_prospect = frappe.db.get_value("Dalili Contact", self.contact, "prospect")
            if contact_prospect and contact_prospect != self.prospect:
                frappe.throw(
                    f"Contact {self.contact} belongs to {contact_prospect}, not {self.prospect}"
                )

    def after_insert(self):
        from dalili.verification import apply_outcome

        apply_outcome(self)

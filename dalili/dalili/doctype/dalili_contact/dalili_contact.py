import frappe
from frappe.model.document import Document

from dalili.logic.normalize import normalize_phone


class DaliliContact(Document):
    """A person at a company, with the compliance fields that make outreach defensible."""

    def validate(self):
        self.phone = normalize_phone(self.phone)
        self.whatsapp = normalize_phone(self.whatsapp) or self.phone
        if self.email:
            self.email = self.email.strip().lower()

        if not self.phone and not self.whatsapp and not self.email:
            frappe.throw("A contact needs at least one of phone, WhatsApp or email")

        if not self.full_name:
            frappe.throw("Full Name is required")

        # PDPA: know on what basis we may contact this person.
        require = frappe.db.get_single_value("Dalili Settings", "require_consent_note")
        if require and not self.consent_basis:
            frappe.throw(
                "Consent Basis is required. Tanzania's Personal Data Protection Act requires a "
                "lawful basis for processing personal data such as a phone number."
            )

        if self._is_suppressed():
            self.do_not_contact = 1
            self.verification_status = "Do Not Contact"

        if self.do_not_contact and self.is_primary:
            self.is_primary = 0

        if not self.next_check_on and self.last_verified_on:
            sla = frappe.db.get_single_value("Dalili Settings", "verification_sla_days") or 30
            self.next_check_on = frappe.utils.add_days(self.last_verified_on, int(sla))

    def _is_suppressed(self) -> bool:
        for suppression_type, value in (
            ("Phone", self.phone or self.whatsapp),
            ("Email", self.email),
        ):
            if not value:
                continue
            if frappe.db.get_value(
                "Dalili Suppression",
                {"suppression_type": suppression_type, "value": value, "is_active": 1},
                "name",
            ):
                return True
        return False

    @frappe.whitelist(methods=["GET"])
    def whatsapp_link(self):
        from dalili.logic.normalize import whatsapp_link

        return whatsapp_link(self.whatsapp or self.phone or "")

from frappe.model.document import Document


class DaliliProspect(Document):
    """A canonical company record: the unit of the entity graph.

    The `normalized_key` is the identity anchor. It is derived from the strongest
    available identifier (BRELA number > TIN > domain > phone > name) and is what
    makes repeated agent runs merge into the same record instead of duplicating it.
    """

    def validate(self):
        from dalili.logic.identity import match_key
        from dalili.logic.normalize import (
            domain_from_website,
            normalize_company_name,
            normalize_phone,
        )

        self.company_name = (self.company_name or "").strip()
        if not self.company_name:
            frappe.throw("Company Name is required")

        self.primary_phone = normalize_phone(self.primary_phone)
        self.primary_whatsapp = normalize_phone(self.primary_whatsapp) or self.primary_phone
        if self.primary_email:
            self.primary_email = self.primary_email.strip().lower()
        if self.website and not self.domain:
            self.domain = domain_from_website(self.website)

        if not self.normalized_key:
            self.normalized_key = match_key(
                brela_number=self.brela_number,
                tin=self.tin,
                domain=self.domain,
                phone=self.primary_phone,
                name=self.company_name,
            )

        self.signal_count = len(self.signals or [])
        self._check_suppression()
        self._stamp_verification()

    def _check_suppression(self):
        """Never let a suppressed phone silently stay contactable."""
        if not self.primary_phone:
            return
        reason = frappe.db.get_value(
            "Dalili Suppression",
            {"suppression_type": "Phone", "value": self.primary_phone, "is_active": 1},
            "reason",
        )
        if reason:
            self.suppressed = 1
            self.suppression_reason = reason
            if self.status not in ("Converted", "Archived"):
                self.status = "Suppressed"

    def _stamp_verification(self):
        if self.last_verified_on and not self.next_verification_on:
            sla = frappe.db.get_single_value("Dalili Settings", "verification_sla_days") or 30
            self.next_verification_on = frappe.utils.add_days(self.last_verified_on, int(sla))

    def before_save(self):
        if not self.legal_name:
            self.legal_name = self.company_name

    def mark_verified(self, when=None):
        """Called by the verification flow."""
        sla = frappe.db.get_single_value("Dalili Settings", "verification_sla_days") or 30
        self.last_verified_on = when or frappe.utils.nowdate()
        self.next_verification_on = frappe.utils.add_days(self.last_verified_on, int(sla))
        self.verification_status = "Verified"
        self.status = "Verified"
        self.save(ignore_permissions=True)


# imported late to keep the module importable outside a bench (tests import logic only)
import frappe  # noqa: E402

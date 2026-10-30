import frappe
from frappe.model.document import Document


class DaliliSuppression(Document):
    """Do-not-contact list. PDPA compliance lives here as much as in the marketing copy.

    Applies to phone numbers, emails, domains and whole companies. Any matching
    contact is automatically marked do-not-contact, and matching prospects are
    excluded from agent runs.
    """

    def validate(self):
        from dalili.logic.normalize import normalize_email, normalize_phone

        if not self.value:
            frappe.throw("Value is required")

        if self.suppression_type == "Phone":
            self.value = normalize_phone(self.value) or self.value
        elif self.suppression_type == "Email":
            self.value = normalize_email(self.value) or self.value.strip().lower()
        else:
            self.value = self.value.strip()

        if not self.added_on:
            self.added_on = frappe.utils.now_datetime()
        if not self.added_by:
            self.added_by = frappe.session.user

        if self.is_active:
            duplicate = frappe.db.get_value(
                "Dalili Suppression",
                {
                    "suppression_type": self.suppression_type,
                    "value": self.value,
                    "is_active": 1,
                    "name": ("!=", self.name),
                },
                "name",
            )
            if duplicate:
                frappe.throw(
                    f"{self.suppression_type} {self.value} is already suppressed ({duplicate})"
                )

    def after_insert(self):
        if self.is_active:
            self.apply()

    def apply(self):
        """Propagate the suppression to any matching contact or prospect."""
        if self.suppression_type == "Phone":
            contacts = frappe.get_all(
                "Dalili Contact",
                filters={"phone": self.value},
                fields=["name", "prospect"],
            )
            for contact in contacts:
                frappe.db.set_value(
                    "Dalili Contact",
                    contact.name,
                    {"do_not_contact": 1, "verification_status": "Do Not Contact"},
                    update_modified=False,
                )
            frappe.db.set_value(
                "Dalili Prospect",
                {"primary_phone": self.value},
                {"suppressed": 1, "suppression_reason": self.reason},
                update_modified=False,
            )

        elif self.suppression_type == "Email":
            frappe.db.set_value(
                "Dalili Contact",
                {"email": self.value},
                {"do_not_contact": 1, "verification_status": "Do Not Contact"},
                update_modified=False,
            )

        elif self.suppression_type == "Domain":
            for prospect in frappe.get_all(
                "Dalili Prospect", filters={"domain": self.value}, fields=["name"]
            ):
                frappe.db.set_value(
                    "Dalili Prospect",
                    prospect.name,
                    {"suppressed": 1, "suppression_reason": self.reason, "status": "Suppressed"},
                    update_modified=False,
                )

        elif self.suppression_type == "Company":
            names = frappe.get_all(
                "Dalili Prospect",
                filters={"company_name": ("like", f"%{self.value}%")},
                fields=["name"],
            )
            for prospect in names:
                frappe.db.set_value(
                    "Dalili Prospect",
                    prospect.name,
                    {"suppressed": 1, "suppression_reason": self.reason, "status": "Suppressed"},
                    update_modified=False,
                )

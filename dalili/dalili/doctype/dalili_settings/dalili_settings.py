import frappe
from frappe.model.document import Document


class DaliliSettings(Document):
    def validate(self):
        total = sum(
            float(x or 0)
            for x in (self.weight_fit, self.weight_signal,
                      self.weight_confidence, self.weight_contactability)
        )
        if total <= 0:
            frappe.throw("Scoring weights must add up to more than zero")

        if self.enabled is None:
            self.enabled = 1

        if not self.phone_country_code:
            self.phone_country_code = "255"

        if self.llm_enabled and not self.llm_api_key:
            frappe.msgprint(
                "LLM is enabled but no API key is set. The agent will silently fall back to "
                "rule-based parsing and skip the 'why now' sentence.",
                indicator="orange",
                alert=True,
            )

        if self.verification_sla_days and int(self.verification_sla_days) < 1:
            frappe.throw("Verification SLA must be at least 1 day")

    @property
    def weights(self):
        return {
            "fit": self.weight_fit or 35,
            "signal": self.weight_signal or 30,
            "confidence": self.weight_confidence or 20,
            "contactability": self.weight_contactability or 15,
        }

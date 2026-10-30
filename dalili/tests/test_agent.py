"""Integration tests — require a bench with a site.

    bench --site <site> run-tests --app dalili
    # or a single module:
    bench --site <site> run-tests --module dalili.tests.test_agent

They exercise the real pipeline against the Demo provider, so no API keys or
network access are needed.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from dalili.agent.orchestrator import execute
from dalili.logic.identity import match_key
from dalili.logic.normalize import normalize_phone


class TestDaliliPipeline(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # make sure reference data exists even on a site where after_install ran long ago
        from dalili.install import seed_data_sources, seed_sectors, seed_signal_types

        seed_sectors()
        seed_signal_types()
        seed_data_sources()
        frappe.db.set_single_value("Dalili Settings", "demo_mode", 1)
        frappe.db.set_single_value("Dalili Settings", "enabled", 1)
        frappe.db.commit()

        cls.icp = frappe.get_doc(
            {
                "doctype": "Dalili ICP",
                "icp_name": "TEST · Hotels Dar es Salaam",
                "status": "Active",
                "sector": "Hospitality & Tourism",
                "region": "Dar es Salaam",
                "target_count": 5,
                "min_score": 20,
                "languages": "Swahili",
            }
        )
        cls.icp.insert(ignore_permissions=True)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.db.delete("Dalili Lead List", {"icp": cls.icp.name})
        frappe.db.delete("Dalili Agent Run", {"icp": cls.icp.name})
        frappe.db.delete("Dalili ICP", {"name": cls.icp.name})
        frappe.db.commit()
        super().tearDownClass()

    def test_icp_created(self):
        self.assertTrue(self.icp.name)
        self.assertEqual(self.icp.target_count, 5)

    def test_pipeline_produces_a_lead_list(self):
        run_name = execute(self.icp.name, triggered_by="Administrator")
        run = frappe.get_doc("Dalili Agent Run", run_name)

        self.assertEqual(run.status, "Completed", msg=run.error_log)
        self.assertTrue(run.lead_list)
        self.assertGreaterEqual(run.discovered, 1)
        self.assertGreaterEqual(run.delivered, 1)

        lead_list = frappe.get_doc("Dalili Lead List", run.lead_list)
        self.assertEqual(lead_list.total_prospects, len(lead_list.items))
        self.assertLessEqual(lead_list.total_prospects, 5)
        self.assertGreater(lead_list.avg_score, 0)

        # steps are recorded as an audit trail
        self.assertGreaterEqual(len(run.steps), 5)

    def test_scoring_is_explainable(self):
        import json

        prospect = frappe.get_all(
            "Dalili Prospect", filters={"total_score": (">", 0)}, fields=["name"], limit=1
        )
        self.assertTrue(prospect, "expected at least one scored prospect")
        doc = frappe.get_doc("Dalili Prospect", prospect[0].name)
        breakdown = json.loads(doc.score_breakdown)
        self.assertIn("components", breakdown)
        self.assertIn("fit", breakdown["components"])
        self.assertIn("reasons", breakdown)

    def test_dedupe_on_second_run(self):
        """Running the same ICP twice must merge, not duplicate."""
        before = frappe.db.count("Dalili Prospect", {"sector": "Hospitality & Tourism"})
        execute(self.icp.name, triggered_by="Administrator")
        after = frappe.db.count("Dalili Prospect", {"sector": "Hospitality & Tourism"})
        self.assertEqual(before, after, "second run should merge into existing prospects")

    def test_verification_updates_contact_and_prospect(self):
        from dalili.verification import log

        contact = frappe.get_all(
            "Dalili Contact",
            filters={"prospect": ("!=", "")},
            fields=["name", "prospect"],
            limit=1,
        )
        self.assertTrue(contact)
        name = log(
            prospect=contact[0].prospect,
            contact=contact[0].name,
            method="Outbound call",
            outcome="Answered - verified",
            notes="test",
        )
        self.assertTrue(name)
        status = frappe.db.get_value("Dalili Contact", contact[0].name, "verification_status")
        self.assertEqual(status, "Verified")

    def test_suppression_blocks_contact(self):
        contact = frappe.get_all("Dalili Contact", fields=["name", "phone"], limit=1)
        if not contact or not contact[0].phone:
            self.skipTest("no contact with a phone to suppress")
        frappe.get_doc(
            {
                "doctype": "Dalili Suppression",
                "suppression_type": "Phone",
                "value": contact[0].phone,
                "reason": "Opt-out",
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Dalili Contact", contact[0].name, "do_not_contact"), 1
        )


class TestPhoneHandling(FrappeTestCase):
    def test_normalisation(self):
        self.assertEqual(normalize_phone("0754 123 456"), "+255754123456")

    def test_match_key_stability(self):
        a = match_key(name="Bahari Hotels Ltd")
        b = match_key(name="BAHARI HOTEL LIMITED")
        self.assertEqual(a, b)

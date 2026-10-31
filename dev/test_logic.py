"""
Standalone tests for the pure-logic layer — runs WITHOUT a Frappe bench.

    cd dalili-app && python3 dev/test_logic.py -v

These are the tests you can run on any machine, in CI, or in a plain REPL. The same
logic is exercised again inside the app by dalili/tests/test_logic.py (which runs
under `bench run-tests` and can therefore also touch the database).
"""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dalili.logic.icp import (  # noqa: E402
    clarifying_questions,
    detect_language,
    parse_prompt,
)
from dalili.logic.identity import (  # noqa: E402
    dedupe_batch,
    find_duplicate,
    match_key,
    merge_into,
    similarity,
)
from dalili.logic.normalize import (  # noqa: E402
    domain_from_website,
    employee_band,
    normalize_company_name,
    normalize_phone,
    whatsapp_link,
)
from dalili.logic.scoring import (  # noqa: E402
    contactability_score,
    fit_score,
    normalise_weights,
    score_prospect,
    signal_score,
    why_now,
)


class TestNormalise(unittest.TestCase):
    def test_phone_variants(self):
        expected = "+255754123456"
        for raw in [
            "+255 754 123 456",
            "00255754123456",
            "255754123456",
            "0754123456",
            "754123456",
            "+255-754-123-456",
            "(0754) 123 456",
        ]:
            self.assertEqual(normalize_phone(raw), expected, msg=raw)

    def test_phone_landline(self):
        self.assertEqual(normalize_phone("022 211 2345"), "+255222112345")

    def test_phone_garbage(self):
        for raw in ["", None, "n/a", "12345", "hello"]:
            self.assertEqual(normalize_phone(raw), "", msg=str(raw))

    def test_company_name(self):
        cases = {
            "Kilimanjaro Foods Ltd.": "kilimanjaro foods",
            "KILIMANJARO FOODS LIMITED": "kilimanjaro foods",
            "Kilimanjaro Foods (Tanzania) Company Limited": "kilimanjaro foods",
            "Raha Energies & Sons": "raha energies",
            "The Bahari Hotel Group": "bahari hotel",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_company_name(raw), expected, msg=raw)

    def test_domain(self):
        self.assertEqual(domain_from_website("https://www.mfano.co.tz/about?x=1"), "mfano.co.tz")
        self.assertEqual(domain_from_website("mfano.co.tz"), "mfano.co.tz")
        self.assertEqual(domain_from_website(""), "")

    def test_whatsapp_link(self):
        self.assertEqual(whatsapp_link("+255754123456"), "https://wa.me/255754123456")
        self.assertTrue(whatsapp_link("+255754123456", "habari").startswith("https://wa.me/255754123456?text="))

    def test_employee_band(self):
        self.assertEqual(employee_band(5), "1-10")
        self.assertEqual(employee_band(30), "11-50")
        self.assertEqual(employee_band(150), "51-200")
        self.assertEqual(employee_band(900), "200+")


class TestIdentity(unittest.TestCase):
    def test_match_key_precedence(self):
        self.assertTrue(match_key(brela_number="123456", name="X").startswith("brela:"))
        self.assertTrue(match_key(tin="111-222-333", name="X").startswith("tin:"))
        self.assertTrue(match_key(domain="mfano.co.tz", name="X").startswith("domain:"))
        self.assertTrue(match_key(phone="0754123456", name="X").startswith("phone:"))
        self.assertTrue(match_key(name="Mfano Ltd").startswith("name:"))

    def test_similarity(self):
        self.assertEqual(similarity("Kilimanjaro Foods Ltd", "KILIMANJARO FOODS LIMITED"), 1.0)
        self.assertGreater(similarity("Bahari Hotel", "Bahari Hotels and Lodges"), 0.7)
        self.assertLess(similarity("Bahari Hotel", "Serengeti Cement"), 0.4)

    def test_find_duplicate_by_domain(self):
        existing = [
            {"company_name": "Bahari Hotel", "domain": "bahari.co.tz"},
            {"company_name": "Serengeti Cement", "domain": "serengeti-cement.co.tz"},
        ]
        idx, score, reason = find_duplicate(
            {"company_name": "Bahari Hotels Ltd", "website": "https://www.bahari.co.tz"},
            existing,
        )
        self.assertEqual(idx, 0)
        self.assertEqual(score, 1.0)
        self.assertIn("domain", reason)

    def test_find_duplicate_by_name(self):
        existing = [{"company_name": "Kilimanjaro Foods Limited", "primary_phone": "0754000111"}]
        idx, score, _ = find_duplicate({"company_name": "Kilimanjaro Foods Ltd"}, existing)
        self.assertEqual(idx, 0)
        self.assertEqual(score, 1.0)

    def test_no_false_positive(self):
        existing = [{"company_name": "Bahari Hotel"}]
        idx, score, _ = find_duplicate({"company_name": "Serengeti Cement"}, existing)
        self.assertIsNone(idx)
        self.assertEqual(score, 0.0)

    def test_acronym_match(self):
        self.assertGreaterEqual(similarity("KFL", "Kilimanjaro Foods Limited"), 0.85)

    def test_dedupe_batch(self):
        batch = [
            {"company_name": "Bahari Hotel", "primary_phone": "0754000111"},
            {"company_name": "BAHARI HOTEL LTD", "primary_phone": ""},
            {"company_name": "Serengeti Cement", "primary_phone": "0754000222"},
        ]
        unique, merges = dedupe_batch(batch)
        self.assertEqual(len(unique), 2)
        self.assertEqual(merges, 1)
        # the merge keeps the phone discovered on the first row
        self.assertEqual(unique[0]["primary_phone"], "0754000111")

    def test_merge_into_never_overwrites(self):
        merged = merge_into({"region": "Arusha", "notes": ""}, {"region": "Mwanza", "notes": "hi"})
        self.assertEqual(merged["region"], "Arusha")
        self.assertEqual(merged["notes"], "hi")


class TestScoring(unittest.TestCase):
    icp = {
        "sector": "Hospitality & Tourism",
        "region": "Dar es Salaam",
        "employee_band_min": 11,
        "employee_band_max": 100,
        "include_keywords": "hotel",
    }

    def test_weights_normalise(self):
        w = normalise_weights({"fit": 1, "signal": 1, "confidence": 1, "contactability": 1})
        self.assertAlmostEqual(sum(w.values()), 100.0, places=6)

    def test_fit_full_match(self):
        out = fit_score(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism",
             "region": "Dar es Salaam", "employee_band": "51-200"},
            self.icp,
        )
        self.assertFalse(out["excluded"])
        self.assertGreater(out["score"], 80)

    def test_fit_exclusion_is_hard(self):
        out = fit_score(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism",
             "region": "Dar es Salaam"},
            {"sector": "Hospitality & Tourism", "exclude_keywords": "bahari"},
        )
        self.assertTrue(out["excluded"])
        self.assertEqual(out["score"], 0.0)

    def test_signal_decay(self):
        today = date(2026, 10, 30)
        fresh = signal_score(
            [{"title": "Won tender", "strength": 15, "detected_on": today}],
            decay_days=90, saturation=40, today=today,
        )
        old = signal_score(
            [{"title": "Won tender", "strength": 15,
              "detected_on": today - timedelta(days=180)}],
            decay_days=90, saturation=40, today=today,
        )
        self.assertGreater(fresh["score"], old["score"])
        self.assertAlmostEqual(fresh["raw"], 15.0, places=2)
        self.assertLess(old["raw"], 4.0)

    def test_contactability_prefers_verified_whatsapp(self):
        out = contactability_score([
            {"full_name": "Asha", "whatsapp": "+255754000111",
             "verification_status": "Verified", "seniority": "Manager"},
            {"full_name": "Juma", "phone": "+255754000222",
             "verification_status": "Unverified", "seniority": "Officer"},
        ])
        self.assertGreater(out["score"], 60)
        self.assertEqual(out["best"], "Asha")

    def test_contactability_respects_opt_out(self):
        out = contactability_score([
            {"full_name": "Asha", "whatsapp": "+255754000111", "do_not_contact": 1},
        ])
        self.assertEqual(out["score"], 0.0)

    def test_score_prospect_explainable(self):
        out = score_prospect(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism",
             "region": "Dar es Salaam", "employee_band": "51-200"},
            self.icp,
            contacts=[{"full_name": "Asha", "whatsapp": "+255754000111",
                       "verification_status": "Verified", "seniority": "Manager"}],
            signals=[{"title": "Won tender", "strength": 15, "detected_on": date.today()}],
            sources=[{"source_label": "demo", "confidence": 80,
                      "retrieved_on": date.today()}],
        )
        self.assertGreater(out["total"], 60)
        self.assertEqual(set(out["components"]), {"fit", "signal", "confidence", "contactability"})
        self.assertTrue(out["reasons"]["fit"])

    def test_fit_is_share_of_stated_criteria(self):
        """A 3-filter ICP that matches all three must read 100, not 78."""
        out = fit_score(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism",
             "region": "Dar es Salaam", "employee_band": "51-200"},
            {"sector": "Hospitality & Tourism", "region": "Dar es Salaam",
             "employee_band_min": 20},
        )
        self.assertAlmostEqual(out["score"], 100.0, places=2)

    def test_fit_partial_match_is_proportional(self):
        """Only the sector matches: 40 earned of 78 available."""
        out = fit_score(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism",
             "region": "Arusha", "employee_band": "1-10"},
            {"sector": "Hospitality & Tourism", "region": "Dar es Salaam",
             "employee_band_min": 20},
        )
        self.assertAlmostEqual(out["score"], round(100 * 40 / 78, 2), places=1)

    def test_fit_without_criteria_is_neutral(self):
        out = fit_score({"company_name": "X"}, {})
        self.assertEqual(out["score"], 70.0)

    def test_hot_band_is_reachable(self):
        """Regression guard: the HOT threshold must be attainable by a strong lead.

        Before recalibration, fit capped at 78 for a normal ICP, so with realistic
        signals and confidence the total could not reach the 80 HOT band and every
        lead in the demo came out COOL/WARM.
        """
        out = score_prospect(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism",
             "region": "Dar es Salaam", "employee_band": "51-200"},
            {"sector": "Hospitality & Tourism", "region": "Dar es Salaam",
             "employee_band_min": 20},
            contacts=[{"full_name": "Asha", "whatsapp": "+255754000111", "phone": "+255754000111",
                       "email": "asha@bahari.co.tz", "verification_status": "Verified",
                       "seniority": "Owner / Founder", "consent_basis": "Public business listing"}],
            signals=[{"title": "Won tender", "strength": 18, "detected_on": date.today()},
                     {"title": "Import shipment", "strength": 15, "detected_on": date.today()}],
            sources=[{"source_label": "demo", "confidence": 85, "retrieved_on": date.today()}],
        )
        self.assertGreaterEqual(out["total"], 80.0, out)

    def test_excluded_prospect_scores_zero(self):
        out = score_prospect(
            {"company_name": "Bahari Hotel", "sector": "Hospitality & Tourism"},
            {"exclude_keywords": "bahari"},
        )
        self.assertTrue(out["excluded"])
        self.assertEqual(out["total"], 0.0)

    def test_why_now(self):
        text = why_now(
            {"sector": "Hospitality & Tourism"},
            [{"title": "Won tender", "strength": 15, "detected_on": date.today()}],
        )
        self.assertIn("Won tender", text)


class TestICP(unittest.TestCase):
    def test_swahili_prompt(self):
        p = parse_prompt(
            "Nipe kampuni 40 za ujenzi Dar es Salaam zenye wafanyakazi zaidi ya 50 "
            "na wamepata tender mwaka huu"
        )
        self.assertEqual(p["sector"], "Construction & Real Estate")
        self.assertEqual(p["region"], "Dar es Salaam")
        self.assertEqual(p["target_count"], 40)
        self.assertEqual(p["employee_band_min"], 50)
        self.assertIn("Tender Award", p["watch_signals"])
        self.assertEqual(p["_language"], "Swahili")
        self.assertEqual(clarifying_questions(p), [])

    def test_english_prompt(self):
        p = parse_prompt(
            "Find 25 hotels in Arusha with more than 20 employees that are hiring"
        )
        self.assertEqual(p["sector"], "Hospitality & Tourism")
        self.assertEqual(p["region"], "Arusha")
        self.assertEqual(p["target_count"], 25)
        self.assertEqual(p["employee_band_min"], 20)
        self.assertIn("Hiring", p["watch_signals"])

    def test_logistics_with_imports(self):
        p = parse_prompt("logistics companies in Dar es Salaam importing containers")
        self.assertEqual(p["sector"], "Transport & Logistics")
        self.assertIn("Shipment / Import", p["watch_signals"])

    def test_size_range(self):
        p = parse_prompt("manufacturers in Mwanza with 20-50 employees")
        self.assertEqual((p["employee_band_min"], p["employee_band_max"]), (20, 50))

    def test_missing_fields_produce_questions(self):
        p = parse_prompt("get me some leads")
        qs = clarifying_questions(p)
        self.assertTrue(any("sector" in q.lower() or "sekta" in q.lower() for q in qs))

    def test_language_detection(self):
        self.assertEqual(detect_language("Nipe kampuni za ujenzi"), "Swahili")
        self.assertEqual(detect_language("Find construction companies"), "English")

    def test_seniority_and_department(self):
        p = parse_prompt("hotels in Dar, talk to the procurement manager")
        self.assertEqual(p["seniority_preference"], "Manager")
        self.assertEqual(p["preferred_department"], "Procurement")

    def test_exclude_keywords(self):
        p = parse_prompt("hotels in Dar es Salaam excluding budget lodges")
        self.assertIn("budget lodges", (p["exclude_keywords"] or ""))


class TestOpenStreetMapRules(unittest.TestCase):
    """The free live source. Parsing must be exact — it is real customer data."""

    def _elements(self):
        return [
            {"type": "node", "id": 1, "tags": {
                "name": "Holiday Inn Dar Es Salaam", "tourism": "hotel",
                "phone": "+255 22 2139250", "addr:city": "Dar es Salaam",
                "addr:street": "Azikiwe Street", "addr:housenumber": "4"}},
            {"type": "way", "id": 2, "tags": {
                "name": "Mbezi Lodge", "tourism": "guest_house",
                "contact:phone": "0677301314 , 0782593226", "addr:suburb": "Kinondoni",
                "website": "https://mbezilodge.co.tz/rooms"}},
            {"type": "node", "id": 3, "tags": {"tourism": "hotel"}},          # no name
            {"type": "node", "id": 4, "tags": {
                "name": "Kariakoo Hardware", "shop": "hardware",
                "email": "SALES@Example.co.tz"}},
        ]

    def test_sector_mapping(self):
        from dalili.logic.osm_rules import sector_for_tags
        self.assertEqual(sector_for_tags({"tourism": "hotel"}), "Hospitality & Tourism")
        self.assertEqual(sector_for_tags({"amenity": "pharmacy"}), "Health")
        self.assertEqual(sector_for_tags({"shop": "hardware"}), "Trade & Retail")
        self.assertEqual(sector_for_tags({"office": "logistics"}), "Transport & Logistics")
        self.assertEqual(sector_for_tags({"name": "x"}), "")

    def test_parse_drops_unnamed_and_normalises(self):
        from dalili.logic.osm_rules import parse_elements
        recs = parse_elements(self._elements(), default_region="Dar es Salaam")
        self.assertEqual(len(recs), 3)                      # unnamed POI dropped
        names = [r["company_name"] for r in recs]
        self.assertNotIn("", names)

        holiday = next(r for r in recs if r["company_name"].startswith("Holiday Inn"))
        self.assertEqual(holiday["primary_phone"], "+255222139250")
        self.assertEqual(holiday["city" if "city" in holiday else "region"], "Dar es Salaam")
        self.assertEqual(holiday["address"], "4 Azikiwe Street")
        self.assertEqual(holiday["sector"], "Hospitality & Tourism")
        self.assertTrue(holiday["source_url"].startswith("https://www.openstreetmap.org/node/1"))

    def test_multi_phone_keeps_first(self):
        from dalili.logic.osm_rules import parse_elements
        recs = parse_elements(self._elements())
        mbezi = next(r for r in recs if r["company_name"] == "Mbezi Lodge")
        self.assertEqual(mbezi["primary_phone"], "+255677301314")
        self.assertEqual(mbezi["domain"], "mbezilodge.co.tz")
        self.assertEqual(mbezi["district"], "Kinondoni")
        self.assertEqual(mbezi["source_id"], "way/2")

    def test_email_lowercased_and_region_default(self):
        from dalili.logic.osm_rules import parse_elements
        recs = parse_elements(self._elements(), default_region="Dar es Salaam")
        hw = next(r for r in recs if r["company_name"] == "Kariakoo Hardware")
        self.assertEqual(hw["primary_email"], "sales@example.co.tz")
        self.assertEqual(hw["region"], "Dar es Salaam")     # from default, not the tags
        self.assertEqual(hw["sector"], "Trade & Retail")

    def test_query_is_valid_overpass_ql(self):
        from dalili.logic.osm_rules import build_query
        q = build_query({"sector": "Hospitality & Tourism", "region": "Dar es Salaam"}, limit=25)
        self.assertIn('area["name"="Dar es Salaam"]', q)
        self.assertIn('["tourism"~"hotel', q)
        self.assertIn("out tags center 25", q)
        # (if: exists(name)) is invalid Overpass QL and returns HTTP 400 — never again
        self.assertNotIn("if: exists", q)

    def test_query_without_region_falls_back_to_country(self):
        from dalili.logic.osm_rules import build_query
        q = build_query({"sector": "Services"}, limit=10)
        self.assertIn('["ISO3166-1"="TZ"]', q)

    def test_unknown_sector_falls_back_to_default_tags(self):
        from dalili.logic.osm_rules import build_query
        q = build_query({"sector": "Mining", "region": "Mwanza"}, limit=10)
        self.assertIn('["office"="company"]', q)


if __name__ == "__main__":
    unittest.main(verbosity=2)

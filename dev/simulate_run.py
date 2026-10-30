"""
End-to-end simulation of the agent pipeline WITHOUT a Frappe bench.

    python3 dev/simulate_run.py "Nipe kampuni 10 za hoteli Dar es Salaam zenye wafanyakazi zaidi ya 20"

It runs the exact modules the app runs — prompt parsing, provider discovery,
entity resolution, scoring — and prints the brief a customer would receive.
This is the fastest way to sanity-check ranking behaviour before touching a bench.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dalili.enrichment.providers.demo import DemoProvider  # noqa: E402
from dalili.logic.icp import parse_prompt  # noqa: E402
from dalili.logic.identity import dedupe_batch  # noqa: E402
from dalili.logic.normalize import whatsapp_link  # noqa: E402
from dalili.logic.scoring import score_prospect, why_now  # noqa: E402

WEIGHTS = {"fit": 35, "signal": 30, "confidence": 20, "contactability": 15}


def run(prompt: str, limit: int = 10) -> None:
    print("=" * 78)
    print("PROMPT:", prompt)
    print("=" * 78)

    parsed = parse_prompt(prompt, {"region": "Dar es Salaam", "target_count": limit})
    print("\n1. PARSED")
    for key in ("sector", "region", "employee_band_min", "employee_band_max",
                "target_count", "watch_signals", "_language"):
        print(f"   {key:22s} {parsed.get(key)}")
    print(f"   {'confidence notes':22s} {parsed.get('_confidence')}")

    filters = {
        "sector": parsed.get("sector") or "",
        "region": parsed.get("region") or "",
        "district": "",
        "employee_band_min": parsed.get("employee_band_min"),
        "employee_band_max": parsed.get("employee_band_max"),
        "include_keywords": parsed.get("include_keywords") or "",
        "exclude_keywords": parsed.get("exclude_keywords") or "",
    }

    provider = DemoProvider()
    result = provider.search(filters, limit=200)
    records = result.records
    print(f"\n2. DISCOVERED  {len(records)} candidates from {provider.source_name}")

    unique, merged = dedupe_batch(records)
    print(f"3. DEDUPED     {len(unique)} unique ({merged} merged)")

    scored = []
    for record in unique:
        signals = [
            {"title": s["title"], "strength": s["strength"], "detected_on": s["detected_on"]}
            for s in record.get("signals", [])
        ]
        # Simulate the state a demo tenant is in after seed.py replays its
        # OUTCOME_MIX verifications: most contacts verified, some not.
        idx = sum(ord(ch) for ch in record["company_name"])
        contacts = [
            {
                "full_name": c["full_name"], "seniority": c["seniority"],
                "phone": c.get("phone"), "whatsapp": c.get("whatsapp"),
                "email": c.get("email"), "role_title": c.get("role_title"),
                "verification_status": "Verified" if (idx + j) % 3 else "Unverified",
                "consent_basis": c.get("consent_basis"),
            }
            for j, c in enumerate(record.get("contacts", []))
        ]
        sources = [
            {
                "source_label": record.get("source_label"),
                "confidence": record.get("confidence", 60),
                "retrieved_on": None,
            }
        ]
        scored.append(
            (score_prospect(record, filters, contacts=contacts, signals=signals,
                            sources=sources, weights=WEIGHTS), record, signals, contacts)
        )

    scored.sort(key=lambda x: x[0]["total"], reverse=True)
    qualified = [row for row in scored if row[0]["total"] >= (parsed.get("min_score") or 45)]
    print(f"4. SCORED      {len(scored)} scored, {len(qualified)} above min score")
    print(f"5. SELECTED    top {min(limit, len(qualified))}")

    print("\n" + "-" * 78)
    print("BRIEF THAT WOULD BE SENT ON WHATSAPP")
    print("-" * 78 + "\n")

    for rank, (score, record, signals, contacts) in enumerate(qualified[:limit], start=1):
        best = max(
            contacts,
            key=lambda c: (
                (10 if c.get("whatsapp") else 0)
                + {"Owner / Founder": 5, "C-Level": 4, "Director": 3, "Manager": 2}.get(
                    c.get("seniority"), 1)
            ),
        )
        number = best.get("whatsapp") or best.get("phone") or ""
        label = "HOT" if score["total"] >= 80 else "WARM" if score["total"] >= 60 else "COOL"
        print(f"{rank}. *{record['company_name']}* [{label} {round(score['total'])}]")
        print(f"   {record['district']}, {record['region']} · {record['employee_band']} staff"
              f" · {record['sub_sector']}")
        print(f"   👤 {best['full_name']} — {best.get('role_title')}")
        print(f"   📱 {number} {'(WhatsApp)' if best.get('whatsapp') else ''}")
        print(f"   ⚡ {why_now(record, signals)}")
        if number:
            print(f"   🔗 {whatsapp_link(number)}")
        print(f"   score: fit {score['components']['fit']:.0f} | "
              f"signal {score['components']['signal']:.0f} | "
              f"confidence {score['components']['confidence']:.0f} | "
              f"contactability {score['components']['contactability']:.0f}")
        print()

    # A ranking must be discriminating: if every score were ~identical the model
    # would be useless in front of a sales manager.
    totals = [row[0]["total"] for row in scored]
    print("-" * 78)
    spread = max(totals) - min(totals)
    print(f"score spread: min {min(totals):.0f} · median {sorted(totals)[len(totals)//2]:.0f}"
          f" · max {max(totals):.0f}  (spread {spread:.0f} pts)")
    # When the ICP filters are coarse (sector + region only) every prospect ties on
    # fit, so the ranking is carried by signals and data confidence. That is
    # expected; a spread under ~8 points would mean the scorer is flat-lining.
    print("ranking is discriminating" if spread > 8 else "WARNING: ranking is flat")
    print(json.dumps({"checked": True}, indent=0)[:20])


if __name__ == "__main__":
    prompt = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Nipe kampuni 10 za hoteli Dar es Salaam zenye wafanyakazi zaidi ya 20 "
             "ambazo zimepata tender"
    )
    run(prompt, limit=10)

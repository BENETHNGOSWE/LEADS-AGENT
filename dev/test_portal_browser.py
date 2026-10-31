"""Browser test for the Dalili portal.

Static checks have now passed three times while the page was broken in the
browser: a 405 on a declared GET verb, then an inline `display:none` that beat
the `.open` class. Both were invisible to py_compile, to the JSON audit, and to
`html.parser`. So this test drives the real DOM in headless Chromium:

    python3 dev/test_portal_browser.py

It renders dalili/www/dalili.html with the Jinja variables stubbed, mocks
`/api/method/*` with fixtures, and asserts on what a person would see.
Exit code is non-zero on any failure.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "dalili" / "www" / "dalili.html"


def render_page() -> str:
    """Strip the Jinja the page needs from Frappe and leave valid HTML."""
    html = PAGE.read_text()
    html = html.replace("{% if demo_mode %}", "").replace("{% endif %}", "")
    html = html.replace('{{ user_fullname.split(" ")[0] }}', "Neema")
    html = re.sub(r"\{\{\s*user_fullname\s*\}\}", "Neema Beneth", html)
    html = re.sub(r"\{\{\s*csrf_token\s*\}\}", "test-csrf", html)
    leftover = re.findall(r"\{\{.*?\}\}|\{%.*?%\}", html)
    assert not leftover, f"unrendered Jinja left in page: {leftover[:3]}"
    return html


BRIEF_TEXT = """📋 Hospitality · Dar es Salaam — 3 leads

1. Zanzibar Beach Resort  (HOT 82.4)
   Zanzibar · 140 staff
   ✅ Verified 2026-10-28 · 📞 +255 777 000 111
   🔗 https://wa.me/255777000111
   💬 Habari, I am reaching out about your restaurant procurement.

2. Kilimanjaro Coffee Lodge  (WARM 71.0)
   Arusha · 60 staff
   🔗 https://wa.me/255777000222
"""

FIXTURES = {
    "dalili.api.stats": {
        "prospects": 56, "verified": 20, "verified_contacts": 35,
        "stale": 5, "verified_rate": 58.3, "contacts": 128, "lead_lists": 6,
    },
    "dalili.api.list_briefs": [
        {"name": "LIST-00001", "list_name": "Hospitality · Dar es Salaam",
         "total_prospects": 15, "verified_count": 4, "status": "Ready"},
        {"name": "LIST-00002", "list_name": "Manufacturing · imports & hiring",
         "total_prospects": 13, "verified_count": 0, "status": "Ready"},
    ],
    "dalili.api.get_brief": {
        "name": "LIST-00001", "list_name": "Hospitality · Dar es Salaam",
        "icp": "Hospitality", "generated_on": "2026-10-31", "content": BRIEF_TEXT,
    },
    "dalili.api.chat": {
        "message": "ok",
        "parsed": {"sector": "Hospitality & Tourism", "region": "Dar es Salaam",
                   "employee_band_min": 20, "target_count": 20, "languages": "Swahili"},
        "questions": ["Tell me the company size — number of employees.",
                      "How many leads do you need this round?"],
        "ready": True, "language": "sw",
    },
    "dalili.api.create_icp": {"icp": "ICP-00007"},
    "dalili.api.run_now": {
        "status": "Completed", "duration_seconds": 3, "lead_list": "LIST-00001",
        "counters": {"discovered": 16, "duplicates_merged": 0, "qualified": 13, "delivered": 13},
        "steps": [{"step": "Discover candidates", "status": "Completed", "in": 16, "out": 16},
                  {"step": "Build lead list", "status": "Completed", "in": 13, "out": 13}],
    },
    "dalili.api.export_csv": {"file_url": "/private/files/LIST.csv"},
}


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed (pip install playwright && playwright install chromium)")
        return 0

    checks: list[tuple[str, bool, str]] = []

    def check(label, ok, detail=""):
        checks.append((label, bool(ok), detail))

    html = render_page()

    class Handler(BaseHTTPRequestHandler):
        """Serves the page at / and fixtures at /api/method/*.

        A real origin matters: `set_content` loads about:blank, where the page's
        relative /api/method/... URLs cannot be parsed at all.
        """
        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                body, ctype = html.encode(), "text/html; charset=utf-8"
            else:
                name = next((m for m in FIXTURES if path.endswith(m)), None)
                payload = {"message": FIXTURES[name]} if name else {"message": None}
                body, ctype = json.dumps(payload).encode(), "application/json"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            self.do_GET()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
        page.wait_for_timeout(600)

        # --- the pipeline cards actually fill in -------------------------------
        tried = page.inner_text("#s-prospects") if page.query_selector("#s-prospects") else ""
        check("pipeline cards render", tried.strip() not in ("", "—", "-"), f"s-prospects={tried!r}")

        # --- briefs list is populated -----------------------------------------
        items = page.query_selector_all("#briefs li[data-name]")
        check("briefs list populated", len(items) == 2, f"{len(items)} item(s)")

        # --- THE BUG: clicking a brief must reveal the panel -------------------
        if items:
            items[0].click()
            page.wait_for_timeout(300)
            visible = page.is_visible("#brief-card")
            display = page.eval_on_selector(
                "#brief-card", "el => getComputedStyle(el).display")
            check("brief panel opens on click", visible and display != "none",
                  f"is_visible={visible} display={display}")

            title = page.inner_text("#brief-title")
            # the heading is CSS-uppercased, so compare case-insensitively
            check("brief title set", "hospitality" in title.lower(), f"title={title!r}")

            body = page.inner_text("#brief-body")
            check("brief body has content", "Zanzibar Beach Resort" in body, f"{len(body)} chars")
            check("brief body has no percent-encoded junk",
                  not re.search(r"%[0-9A-F]{2}", body), body[:80])

            # links are tappable, and styled as part of the text block
            links = page.query_selector_all("#brief-body a")
            check("wa.me links are anchors", len(links) == 2, f"{len(links)} anchor(s)")
            if links:
                deco = links[0].evaluate("el => getComputedStyle(el).textDecorationLine")
                colour = links[0].evaluate("el => getComputedStyle(el).color")
                check("links inherit text colour", colour in
                      page.eval_on_selector("#brief-body", "el => getComputedStyle(el).color"),
                      f"link={colour}")

            # close by button, by scrim, and by Escape
            page.click("#close-brief")
            page.wait_for_timeout(200)
            check("close button hides brief", not page.is_visible("#brief-card"))

            items[0].click()
            page.wait_for_timeout(200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            check("Escape closes brief", not page.is_visible("#brief-card"))

            # body scroll restores (no stuck locked page)
            overflow = page.evaluate("document.body.style.overflow")
            check("page scroll restored on close", overflow in ("", "auto"), f"overflow={overflow!r}")

        # --- chat: parsed table + questions as a readable list -----------------
        page.fill("#prompt", "nipatie hoteli 20 Dar")
        page.press("#prompt", "Enter")
        page.wait_for_timeout(500)
        convo = page.inner_text("#messages")
        check("chat shows parsed criteria", "Hospitality & Tourism" in convo, "")
        check("clarifying questions are line-separated",
              "• Tell me the company size" in convo, "")

        # --- the run button, then "Open the brief" — the path the user used ----
        if page.query_selector("#confirm-run"):
            page.click("#confirm-run")
            page.wait_for_timeout(600)
            opened = page.is_visible("#brief-card")
            body = page.inner_text("#brief-body") if opened else ""
                # the action button must be inside the visible scroll area
            if page.query_selector("#open-brief-now"):
                box = page.eval_on_selector("#open-brief-now", """el => {
                    const b = el.getBoundingClientRect(), m = document.querySelector('#messages').getBoundingClientRect();
                    return {top: b.top, bot: b.bottom, mtop: m.top, mbot: m.bottom};
                }""")
                visible_btn = box["top"] >= box["mtop"] - 1 and box["bot"] <= box["mbot"] + 1
                check("open-brief button is in view", visible_btn,
                      f"btn {box['top']:.0f}-{box['bot']:.0f} in pane {box['mtop']:.0f}-{box['mbot']:.0f}")
            check("run auto-opens the brief", opened, f"is_visible={opened}")
            check("run brief has the leads", "Zanzibar Beach Resort" in body, "")

        page.screenshot(path=str(ROOT / "dev" / "portal-browser-proof.png"), full_page=False)
        browser.close()
    server.shutdown()

    print("\n  DALILI PORTAL — BROWSER TEST\n")
    failed = 0
    for label, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label:<44} {detail}")
        failed += 0 if ok else 1
    real_errors = [e for e in errors if "favicon" not in e.lower()]
    if real_errors:
        print("\n  console/page errors:")
        for e in real_errors[:6]:
            print(f"    ! {e[:160]}")
        failed += 1
    print(f"\n  {len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

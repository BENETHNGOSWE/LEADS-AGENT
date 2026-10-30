# Dalili — AI Lead Engine for ERPNext v16

> Describe your ideal customer in Swahili or English. Get back verified Tanzanian
> companies, the decision-maker's WhatsApp number, and a specific reason to call
> them this week.

Dalili is a Frappe/ERPNext v16 app. It is the "find them" product that Tanzanian
directories don't sell: an outbound lead engine with entity resolution, a source
waterfall, explainable scoring, a verification loop and a WhatsApp-ready brief —
with verified companies handed straight into ERPNext's CRM.

**Runs with zero API keys.** Demo Mode ships a synthetic company universe so you
can install, click through the whole pipeline and read a real brief in five minutes.

---

## 1. Requirements

| Component | Version | Notes |
|---|---|---|
| Frappe Framework | **v16** | `version-16` branch |
| ERPNext | **v16** | required for the CRM hand-over (`Lead`) |
| Python | **3.14** | required by Frappe v16 itself. The *app package* declares `>=3.10` so `pip install -e .` never blocks a bench that is still on 3.13/3.12 — it does not relax Frappe's own requirement. |
| Node.js | **24** | for `bench build` |
| MariaDB | 10.6+ | Redis 7 recommended |
| bench | latest | standard install |

> Frappe v16 will not run on Python 3.11/3.12 — if you see a `SyntaxError` on a
> `type X = ...` alias, your bench virtualenv is on the wrong Python.

---

## 1b. Frappe version compatibility (verified, not assumed)

Built against **v16**, audited field-by-field against **v15**'s own schema files
(`frappe/core/doctype/doctype`, `docfield`, `report`, `printing/doctype/print_format`
from the `version-15` branch):

| Artifact | v15 result |
|---|---|
| 16 DocType JSONs | All top-level and DocField keys valid |
| 2 Report JSONs | Valid (removed a stray `letterhead` key) |
| 1 Print Format JSON | Valid |
| `@frappe.whitelist(methods=[...])` | Supported — v15 signature is `whitelist(allow_guest=False, xss_safe=False, methods=None)` |
| Python syntax | 3.10+ only; nothing PEP 695, no `match`-only constructs |
| `naming_rule` | Set explicitly (`By "Naming Series" field` / `By fieldname`) rather than inferred |

So the app installs on **either v15 or v16**. Nothing in it is v16-only. Write it up
that way and stop claiming a version you haven't booted: the honest statement is
"schema-validated against v15 and v16 property sets; runtime-tested only where your
bench has actually run it."

## 2. Install (5 minutes)

```bash
cd ~/frappe-bench

# 1. from the unzipped folder (path form works fine)
bench get-app dalili /full/path/to/dalili-app

# 2. install on your site
bench --site yoursite.local install-app dalili

# 3. build assets (v16 uses Vite; this also links /assets/dalili)
bench build --app dalili

# 4. restart
bench restart
```

Then seed the demo tenant:

```bash
bench --site yoursite.local execute dalili.demo.seed.run
```

You should see something like:

```
Demo seeded: 3 ICPs, 3 agent runs, 34 prospects, 61 contacts,
61 verifications, 3 lead lists.
```

### Where to look first

| What | Where |
|---|---|
| **Agent chat + brief** | `https://yoursite/dalili` |
| ICPs (saved searches) | Desk → search **Dalili ICP** |
| Prospects (the entity graph) | Desk → **Dalili Prospect** |
| Lead lists (the deliverable) | Desk → **Dalili Lead List** → button **Copy WhatsApp brief** |
| Run audit trail | Desk → **Dalili Agent Run** (per-stage counters + log) |
| Verification funnel | Desk → **Dalili Verification Funnel** report |
| ICP performance | Desk → **Dalili ICP Performance** report |
| Settings | Desk → **Dalili Settings** |

Two role levels are created on install: **Dalili Manager** (full) and
**Dalili Agent** (create/read/write, no delete).

---

## 3. Try the whole loop in 60 seconds

1. Open `/dalili`.
2. Tap a suggestion chip, or type:
   `Nipe kampuni 12 za hoteli Dar es Salaam zenye wafanyakazi zaidi ya 20`
3. The agent shows what it parsed → **Run agent**.
4. Watch the run card: discovered → merged → qualified → delivered, with the
   per-stage log.
5. The brief opens on the right. **Copy for WhatsApp** gives you the exact text a
   salesperson would receive.
6. Open a Prospect → **Log verification** → choose `Answered - verified`.
   The contact, the prospect, the freshness date and the funnel all update.
7. Log `Disconnected` on a lead in a list → a free replacement is pulled in
   automatically (the "replace-or-refund" policy).

---

## 4. How it maps onto Apollo (what was copied, what was deliberately not)

You asked me to study Apollo and the modern lead-gen stack. Here is the honest
mapping — Apollo's *packaging* is good, its *data model* does not survive contact
with Tanzania.

| Apollo concept | Dalili equivalent | Why |
|---|---|---|
| Saved search / filter set | **Dalili ICP** | Same idea, but created from a sentence, not 40 dropdowns |
| Database (275M contacts) | **Dalili Prospect** + contacts = a *graph you build*, not a database you buy | No credible TZ database exists; you have to assemble it |
| Enrichment credits | `Agent Run.cost_estimate` + per-source `cost_per_call` | Costs are visible per run, not hidden in a credit pool |
| Waterfall enrichment (Clay) | `dalili/enrichment/waterfall.py` | Chained providers, stop at first fill, every fill traced to a source |
| Intent / buying signals | `Dalili Signal Type` + `Dalili Signal` with exponential decay | TZ-specific triggers: NeST tenders, imports, hiring, licensing |
| Lists | **Dalili Lead List** | The deliverable is a brief + CSV, not an export button |
| Sequences / email sending | **Not built on purpose** | Cold email is the wrong channel here; WhatsApp/phone is. And AI SDR email is the most commoditised, highest-churn layer in the market |
| CRM sync | `dalili.integration.convert()` → ERPNext `Lead` | ERPNext already owns the CRM |
| Data accuracy claims | `Dalili Verification` + published verified-rate | The moat is the outcome log, not the record count |

**What is deliberately absent:** bulk email blasting, LinkedIn scraping, and any
feature whose only value is volume. Those are the parts of Apollo that are being
eaten by AI. The parts that survive are data freshness, distribution and trust —
which is where this app concentrates.

---

## 5. Architecture

```
dalili/
├── hooks.py                     app config, doc_events, scheduler
├── install.py                   idempotent bootstrap: roles, sectors, signals, sources, custom fields
├── api.py                       whitelisted endpoints (v16: explicit HTTP methods)
├── logic/                       ← PURE PYTHON, no frappe import, unit-tested
│   ├── normalize.py             phones → E.164 (+255), company-name canonicalisation, domains
│   ├── identity.py              entity resolution: match keys, fuzzy similarity, merge, batch dedupe
│   ├── scoring.py               explainable fit / signal-decay / confidence / contactability
│   └── icp.py                   Swahili+English prompt → structured ICP filters
├── enrichment/
│   ├── waterfall.py             discovery fan-out + enrichment waterfall
│   └── providers/
│       ├── base.py              provider interface + runtime loader by Data Source priority
│       ├── demo.py, demo_pool.py  synthetic universe (fictional)
│       ├── google_places.py     official Places API v1 (never a scraper)
│       ├── registry.py          BRELA/TRA-style CSV import + matching
│       └── llm.py               "why now" prose + ICP refinement only — never facts
├── agent/
│   ├── orchestrator.py          the 10-stage pipeline + audit trail
│   └── tasks.py                 queued runs, daily staleness, weekly digest
├── verification.py              outcome → contact/prospect/suppression + free replacement
├── brief.py                     WhatsApp text / printable HTML / CSV
├── integration.py               ERPNext Lead creation + custom fields
├── demo/seed.py                 run / purge / reset demo data
├── dalili/doctype/              16 DocTypes
├── dalili/report/               2 script reports (verification funnel, ICP performance)
├── dalili/print_format/         "Dalili Lead Brief" Jinja PDF
└── www/dalili.html              the agent chat page (self-contained, no build step)
```

### The pipeline

```
ICP → discover (providers) → entity resolution → upsert → enrich (waterfall)
    → signals → contacts → score → select → lead list
```

Every stage writes a `Dalili Agent Step` with in/out counts and a log, so a user can
see *why* a run returned 7 leads and not 50.

### Scoring (explainable, weighted, tunable)

```
total = fit(35%) + signal(30%) + data_confidence(20%) + contactability(15%)
```

* **Fit** — sector, region, district, employee band, revenue band, keywords.
  Exclusion keywords are a hard zero, not a penalty.
* **Signal** — evidence with exponential decay: a tender award today is worth full
  weight; the same award 180 days ago is worth ~13%. Weights and decay per signal
  type are configurable.
* **Confidence** — source reliability × recency, plus a bonus for independent
  corroboration.
* **Contactability** — verified WhatsApp/phone/email, seniority, consent basis;
  contacts who opted out score zero.

Every score is stored as JSON on the prospect (`score_breakdown`) and rendered as a
table on the form. Nothing is a black box.

---

## 6. Data sourcing & compliance (read this before going live)

Tanzania's **Personal Data Protection Act 2022** is enforced: controllers and
processors must register with the PDPC, appoint a DPO, and get a permit for
cross-border transfers. Penalties reach TZS 100M. This app is built to make
compliance *possible*, not to pretend it is automatic.

What the app does for you:

* **Consent basis is required** on every contact (`Dalili Settings → Require Consent
  Basis`), with the lawful-basis options spelled out.
* **Suppression list** (`Dalili Suppression`) — phone/email/domain/company. A
  suppressed number can never be contacted: the contact is flagged, and the prospect
  is blocked at conversion time.
* **No scraping.** Google Places is used through its official API. Scraping Maps
  violates their terms and gets keys killed — a data business cannot be built on a
  supply line that can be cut off.
* **No LLM-sourced facts.** The model writes the "why now" sentence and refines a
  query. Phone numbers, names and addresses only ever come from a retrieved source,
  and every field on a prospect is traceable to a `Dalili Source Ref` with a
  timestamp.

What you must still do:

1. Register with the **PDPC** before processing personal data in production.
2. Appoint a **DPO**, and keep the quarterly compliance reports.
3. Get a **PDPC permit** if personal data leaves Tanzania (e.g. an LLM or enrichment
   API hosted abroad). If that is slow, self-host an OpenAI-compatible model and
   point `llm_base_url` at it — the app does not care.
4. Make sure the *customer* is the party responsible for their own outreach, and
   that they honour opt-outs. The brief tells them to reply `BAD <n>`, which is a
   suppression, not a support ticket.

---

## 7. Turning on real data

Everything below is off by default so the app never fails on a missing key.

### Google Places (discovery)

1. Desk → **Dalili Data Source** → `Google Places`.
2. Paste the API key, set **Enabled**, priority `10`.
3. Disable `Demo Places`.
4. `Dalili Settings` → **Demo Mode** = off.

### BRELA / TRA exports (identity)

1. Export a CSV with at least a company-name column. Accepted aliases include
   `company_name / company / name / business_name / jina`, plus optional
   `brela_number, tin, region, district, phone, email, website, sector`.
2. Either point the `BRELA Register` source's **Endpoint** at the file path, or call:

```bash
bench --site yoursite.local execute frappe.get_attr --args '["dalili.api.import_registry_csv"]'
```

…or simply POST the CSV to `/api/method/dalili.api.import_registry_csv` from the UI
of your choice. The importer normalises phones, derives domains and merges into
existing prospects using the same entity resolution as the agent.

### Trade / tender / job signals

The provider interface is three methods (`search`, `enrich`, plus a `source_type`).
To add a source, subclass `BaseProvider`, drop it in
`dalili/enrichment/providers/`, and register its `source_type` in
`load_providers()`. Signals are attached as child rows, so a new source never
touches the scoring model.

### LLM (optional)

`Dalili Settings → LLM Enabled`, base URL, model, key. Any OpenAI-compatible
endpoint works (OpenAI, Azure, Groq, Together, a local vLLM). With it off, the
rule-based parser and the deterministic "why now" both still work.

---

## 8. API

All endpoints are whitelisted with explicit methods (Frappe v16 requirement).
Session-authenticated; API keys/tokens work as usual.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `dalili.api.chat` | parse a request → proposed ICP + clarifying questions |
| POST | `dalili.api.preview` | 5 sample companies before committing |
| POST | `dalili.api.create_icp` | create the ICP (optionally run) |
| POST | `dalili.api.enqueue_run` | queue an agent run (long queue) |
| POST | `dalili.api.run_now` | run synchronously |
| GET | `dalili.api.get_run` | status, counters, per-stage log |
| GET | `dalili.api.list_briefs` | recent lead lists |
| GET | `dalili.api.get_brief` | brief as `text` / `html` / `csv` |
| GET/POST | `dalili.api.export_csv` | CSV as a private File |
| POST | `dalili.api.mark_delivered` | delivery audit |
| POST | `dalili.api.log_verification` | record an outcome (drives everything) |
| GET | `dalili.api.verification_summary` | verified rate, bad-lead rate |
| POST | `dalili.api.convert` | create the ERPNext Lead |
| POST | `dalili.api.suppress` | add to the do-not-contact list |
| POST | `dalili.api.import_registry_csv` | bulk import a registry export |
| GET | `dalili.api.stats` | dashboard numbers |

Example:

```bash
curl -X POST https://yoursite/api/method/dalili.api.chat \
  -H "Authorization: token KEY:SECRET" -H "Content-Type: application/json" \
  -d '{"message":"Nipe kampuni 20 za ujenzi Dar es Salaam zenye wafanyakazi zaidi ya 50"}'
```

---

## 9. Testing

```bash
# 1. Pure logic — no bench, no DB, no network (36 tests)
python3 dalili/tests/test_logic.py -v

# 1b. Full pipeline dry run — no bench, no DB, no network
#     (parse prompt -> discover -> dedupe -> score -> print the brief)
python3 dev/simulate_run.py
python3 dev/simulate_run.py "Find 12 manufacturers in Tanzania with more than 20 employees"

# 2. Inside a bench (DB-backed pipeline, entity resolution, verification)
bench --site yoursite.local run-tests --module dalili.tests.test_logic
bench --site yoursite.local run-tests --module dalili.tests.test_agent
```

The logic tests cover the parts most likely to be subtly wrong: phone shapes
(`0754…`, `+255…`, `00255…`, `754…`), company-name canonicalisation, acronym
matching (`KFL` ↔ `Kilimanjaro Foods Limited`), duplicate detection, signal decay,
opt-out handling, and Swahili/English prompt parsing.

`dev/simulate_run.py` is the fastest way to judge whether the *ranking* is sane:
it runs the real modules end to end against the demo universe and prints the brief
a customer would receive. Four bugs were caught this way during the build — a
phone generator that produced only 10 unique numbers across 96 companies (so the
resolver merged genuinely different firms), `wafanyakazi` leaking into
`include_keywords` (which would have silently zeroed real queries), a missing
Swahili `kati ya 20 na 50` range pattern, and a fit formula that capped at 78 so
the HOT band was unreachable.

---

## 10. Demo data

```bash
bench --site site execute dalili.demo.seed.run      # seed
bench --site site execute dalili.demo.seed.purge    # remove demo records only
bench --site site execute dalili.demo.seed.reset    # purge + reseed
```

**All demo companies and people are fictional.** Phone numbers use the
`+255 74X 000 0XX` shape specifically so they are recognisable as placeholders.
Never treat demo output as real business data. Prospects created by the demo carry
`is_demo = 1` so `purge()` leaves real data untouched.

---

## 11. Validation status (be honest with yourself about this)

Done in the authoring environment, and reproducible on your machine:

* ✅ All 16 DocType JSONs parse, have unique fieldnames, and `field_order` matches
  `fields` exactly.
* ✅ Every Python file compiles (`python -m py_compile` across the app).
* ✅ 36 pure-logic unit tests pass, including the Swahili parser and the phone/
  identity edge cases (five real bugs were found and fixed this way).
* ✅ The full pipeline runs without a bench (`dev/simulate_run.py`) and produces a
  ranked, explained brief with a 10–21 point score spread across 4 ICP shapes.
* ✅ Print-format JSON parses; Jinja is standard.

**Not** executed in the authoring environment, because a Frappe v16 bench needs
Python 3.14 + Node 24 + MariaDB + Redis: the actual `bench install-app`, `migrate`,
the doctype sync, and the DB-backed test module. Run those first — if anything
trips, it will be in that boundary, and the two most likely culprits are listed
below.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: dalili` | app not installed into the bench env | `bench --site site install-app dalili`, then `bench build` |
| DocType not found after update | schema not synced | `bench --site site migrate --skip-search-index` |
| `/dalili` returns 404 | `enable_portal` off, or not logged in | enable in Dalili Settings; log in first |
| Agent run fails "No candidates found" | Demo Mode off and no provider configured | re-enable Demo Mode, or add a Places API key and enable that source |
| `Lead` custom fields missing | neither `Lead` nor `CRM Lead` exists on the site | install ERPNext (or `frappe/crm`); fields are created on migrate |
| Custom field creation errors in Error Log | fieldname clash with an existing customisation | rename the conflicting `dalili_*` field; the app only logs, it never blocks install |

---

## 12. Roadmap (what I would build next, in order)

1. **WhatsApp Business Platform delivery** — send the brief and capture replies as
   outcomes automatically (needs a BSP and template approval).
2. **A real Places + trade-data adapter with caching** — cache aggressively; Places
   bills per request and the waterfall will hammer it without a cache layer.
3. **Signal ingestion jobs per source** — NeST tender scraper (public, but not
   machine-readable), job boards, import manifests.
4. **Map view** — ward-level density for FMCG/outlet-census customers.
5. **Team assignment + call queues** — round-robin leads to reps with a daily target.
6. **Marketplace mode** — companies claim their profile and self-verify, which feeds
   the graph from the supply side (and creates the directory flywheel as a by-product).

---

## 13. Honest limitations

* **Demo data is synthetic.** Nothing in Demo Mode is a real business.
* **The agent is Claude/GPT-shaped but not AI-dependent.** Parsing and scoring are
  deterministic by design — cheap, auditable and offline-capable. The LLM only adds
  prose and gap-filling. That is a feature, not a shortcut.
* **Tanzania-only assumptions** live mostly in `logic/icp.py` (regions, sector
  keywords, Swahili) and `normalize.py` (default country code). Both are constants —
  porting to Kenya/Uganda is a taxonomy exercise, not a rewrite.
* **No billing.** Pricing (TZS/month + per-lead) is out of scope here; the cost
  counters are already per-run so metering would be additive.
* **Single-company tenancy.** One site = one customer's data, which is the right
  default under PDPA. Multi-tenant would need row-level permission rules.

---

## 14. Licence

MIT. Built on Frappe Framework and ERPNext (GPLv3) — run it accordingly.

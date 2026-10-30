"""Turn a free-text request (English or Swahili) into structured ICP filters.

    "Nipe kampuni 40 za ujenzi Dar es Salaam zenye wafanyakazi zaidi ya 50
     na wamepata tender mwaka huu"
        -> {sector: Construction & Real Estate, region: Dar es Salaam,
            employee_band_min: 50, target_count: 40, watch_signals: [Tender Award]}

This is deliberately rule-based and deterministic: it works with no API key, costs
nothing, and every extraction can be explained back to the user. If the LLM is
enabled, `dalili.enrichment.providers.llm` can refine the result, but the app never
*depends* on it.
"""

from __future__ import annotations

import re

from dalili.logic.normalize import squash

TANZANIA_REGIONS = [
    "Arusha", "Dar es Salaam", "Dodoma", "Geita", "Iringa", "Kagera", "Katavi",
    "Kigoma", "Kilimanjaro", "Lindi", "Manyara", "Mara", "Mbeya", "Morogoro",
    "Mtwara", "Mwanza", "Njombe", "Pemba", "Pwani", "Rukwa", "Ruvuma", "Shinyanga",
    "Simiyu", "Singida", "Songwe", "Tabora", "Tanga", "Unguja", "Zanzibar",
]

REGION_ALIASES = {
    "dar": "Dar es Salaam",
    "dsm": "Dar es Salaam",
    "dar es salaam": "Dar es Salaam",
    "dar-es-salaam": "Dar es Salaam",
    "zanzibar": "Zanzibar",
    "unguja": "Unguja",
    "pemba": "Pemba",
    "stone town": "Zanzibar",
    "moshi": "Kilimanjaro",
    "arusha": "Arusha",
    "mwanza": "Mwanza",
    "dodoma": "Dodoma",
    "mbeya": "Mbeya",
    "tanga": "Tanga",
    "morogoro": "Morogoro",
    "durban": "Dar es Salaam",  # common typo in inbound requests
}

# keyword -> canonical Dalili Sector name (must match the seeded taxonomy)
SECTOR_KEYWORDS = {
    "Hospitality & Tourism": [
        "hotel", "hoteli", "lodge", "restaurant", "migahawa", "resort", "tourism",
        "utalii", "guest house", "catering", "bar", "cafe", "café",
    ],
    "Health": [
        "hospital", "ospitali", "clinic", "kliniki", "pharmacy", "duka la dawa",
        "diagnostic", "laboratory", "medical", "health", "afya", "dental",
    ],
    "Education": [
        "school", "shule", "college", "chuo", "university", "universiti", "academy",
        "training", "mafunzo", "kindergarten", "daycare",
    ],
    "Construction & Real Estate": [
        "construction", "ujenzi", "contractor", "mkandarasi", "real estate",
        "property", "ardhi", "cement", "civil works", "building", "hardware",
    ],
    "Manufacturing": [
        "manufacturer", "kiwanda", "factory", "processing", "uzalishaji", "plant",
        "packaging", "vifungashio", "bottling", "milling", "brewery",
    ],
    "Transport & Logistics": [
        "logistics", "transport", "usafirishaji", "clearing", "forwarding",
        "freight", "trucking", "cargo", "mizigo", "shipping", "courier", "boda",
    ],
    "ICT & Media": [
        "ict", "software", "it company", "technology", "teknolojia", "isp",
        "internet", "telecom", "media", "radio", "tv", "digital agency", "pos",
        "payment", "fintech", "saas", "cyber",
    ],
    "Financial Services": [
        "bank", "benki", "insurance", "bima", "microfinance", "sacco", "lending",
        "credit", "broker", "asset management", "mobile money",
    ],
    "Agriculture": [
        "agriculture", "kilimo", "agro", "farm", "shamba", "coffee", "kahawa",
        "sisal", "cashew", "horticulture", "livestock", "mifugo", "seed",
    ],
    "Energy & Utilities": [
        "solar", "energy", "nishati", "power", "umeme", "generator", "fuel",
        "petrol", "gas", "water", "maji", "oil",
    ],
    "Trade & Retail": [
        "supermarket", "retail", "duka", "wholesale", "jumla", "distributor",
        "msambazaji", "traders", "supplies", "shop", "store", "boutique",
    ],
    "Public Sector": ["government", "serikali", "municipal", "council", "halmashauri",
                      "authority", "ngo", "asasi"],
    "Services": [
        "cleaning", "usafi", "security", "ulizi", "consulting", "ushauri",
        "accounting", "audit", "legal", "law firm", "advertising", "marketing",
        "printing", "printing", "events", "hr", "recruitment", "facility",
    ],
}

SIGNAL_KEYWORDS = {
    "Tender Award": ["won tender", "wamepata tender", "tender award", "contract awarded",
                     "zabuni", "tender"],
    "Hiring": ["hiring", "ajira", "job posting", "wanaajiri", "recruiting",
               "new staff", "vacancy", "nafasi"],
    "Shipment / Import": ["import", "kuagiza", "shipment", "container", "mzigo",
                          "bill of lading", "customs"],
    "Expansion": ["new branch", "taa mpya", "expansion", "kupanua", "new warehouse",
                  "opening", "kufungua"],
    "Licence": ["licence", "license", "kibali", "permit", "leseni"],
    "Funding": ["funding", "investment", "mwekezaji", "raised", "mkopo", "loan",
                "grant", "capital"],
    "Registration": ["newly registered", "new registration", "usajili mpya",
                     "registered this year"],
    "Leadership Change": ["new ceo", "new md", "mkurugenzi mpya", "appointed",
                          "new manager"],
    "Social Activity": ["active on instagram", "social media", "anatangaza", "advertising"],
    "Website Change": ["new website", "tovuti mpya", "launched website"],
}

SENIORITY_KEYWORDS = {
    "Owner / Founder": ["owner", "founder", "mmiliki", "mwenye", "proprietor"],
    "C-Level": ["ceo", "md", "managing director", "mkurugenzi mkuu", "cfo", "coo", "cto"],
    "Director": ["director", "mkurugenzi", "head of"],
    "Manager": ["manager", "meneja", "supervisor"],
    "Officer": ["officer", "afisa", "clerk", "assistant"],
}

DEPARTMENT_KEYWORDS = {
    "Procurement": ["procurement", "manunuzi", "purchasing", "buyer", "ununuzi"],
    "Finance": ["finance", "accountant", "mhasibu", "accounts", "fedha"],
    "Operations": ["operations", "uendeshaji", "production", "logistics"],
    "Sales": ["sales", "mauzo", "marketing"],
    "IT": ["it", "ict", "systems", "network"],
    "HR": ["hr", "human resource", "watuperson", "personnel"],
}

_SW_INDICATORS = {
    "nipe", "nataka", "kampuni", "wafanyakazi", "zaidi", "ya", "kwa", "na", "za",
    "wenye", "wamepata", "tafuta", "tafadhali", "mimi", "natakiwa", "biashara",
    "mkoa", "wilaya", "mzigo", "mauzo", "wateja", "leo", "kesho",
}

_NUMBER_WORDS = {
    "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5, "sita": 6, "saba": 7,
    "nane": 8, "tisa": 9, "kumi": 10, "ishirini": 20, "thelathini": 30,
    "arobaini": 40, "hamsini": 50, "sitini": 60, "sabini": 70, "themanini": 80,
    "tisini": 90, "mia moja": 100,
}


def _find_sector(text: str) -> tuple[str | None, str | None]:
    best, best_hits = None, 0
    for sector, keywords in SECTOR_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best, best_hits = sector, hits
    return best, None


def _find_region(text: str) -> str | None:
    for alias, canonical in sorted(REGION_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return canonical
    for region in TANZANIA_REGIONS:
        if squash(region) in text:
            return region
    return None


def _find_signals(text: str) -> list[str]:
    found = []
    for signal, keywords in SIGNAL_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(signal)
    return found


def _find_seniority(text: str) -> tuple[str | None, str | None]:
    for seniority, keywords in SENIORITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return seniority, None
    return None, None


def _find_department(text: str) -> str | None:
    for dept, keywords in DEPARTMENT_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords):
            return dept
    return None


def _find_count(text: str) -> int | None:
    # "kampuni 40", "40 companies", "leads 50", "nataka 30"
    patterns = [
        r"(?:kampuni|companies|company|leads|mashirika|wateja|records)\s*(?:za|ya|of)?\s*(\d{1,4})",
        r"(\d{1,4})\s*(?:kampuni|companies|company|leads|records|mashirika)",
        r"top\s*(\d{1,4})",
        r"nipe\s*(\d{1,4})",
    ]
    # "Find 25 hotels", "nipe 40", "get me 10 leads"
    patterns.append(r"(?:find|get|give me|show me|nipe|nataka|tafuta|list|fetch|need|want|looking for)\s+(?:me\s+)?(?:about\s+|around\s+)?(\d{1,4})")
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            value = int(m.group(1))
            if 1 <= value <= 2000:
                return value
    for word, value in sorted(_NUMBER_WORDS.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(word)}\b\s*(?:kampuni|companies|leads)?", text):
            return value
    return None


def _find_size(numeric_text: str) -> tuple[int | None, int | None]:
    """Extract employee bounds: 'zaidi ya 50', 'more than 50 employees', '20-50', '11 to 50'.

    `numeric_text` must preserve hyphens (squash() strips them, turning '20-50'
    into '20 50' and breaking range detection).
    """
    text = numeric_text
    # "kati ya 20 na 50 wafanyakazi" / "between 20 and 50 employees"
    m = re.search(
        r"(?:kati\s+ya|between)\s*(\d{1,4})\s*(?:na|and|-|to)\s*(\d{1,4})", text
    )
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))

    # explicit range
    m = re.search(r"(\d{1,4})\s*(?:-|to|hadi)\s*(\d{1,4})\s*(?:employees|wafanyakazi|staff|watu)", text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))

    patterns_min = [
        r"(?:zaidi ya|more than|over|above|at least|kupita)\s*(\d{1,4})",
        r"(\d{1,4})\s*\+\s*(?:employees|wafanyakazi|staff)",
        r"(?:employees|wafanyakazi|staff)\s*(?:zaidi ya|more than|above)\s*(\d{1,4})",
    ]
    for pattern in patterns_min:
        m = re.search(pattern, text)
        if m:
            return (int(m.group(1)), None)

    patterns_max = [
        r"(?:chini ya|less than|under|below|fewer than)\s*(\d{1,4})",
        r"(?:employees|wafanyakazi|staff)\s*(?:chini ya|less than|under)\s*(\d{1,4})",
    ]
    for pattern in patterns_max:
        m = re.search(pattern, text)
        if m:
            return (None, int(m.group(1)))

    m = re.search(r"(\d{1,4})\s*(?:employees|wafanyakazi|staff)", text)
    if m:
        return (int(m.group(1)), None)
    return (None, None)


# Words that describe the *shape* of a request rather than a distinguishing
# attribute of a company. If one of these leaks into include_keywords, every
# prospect is penalised for not having it in its name — so "zenye wafanyakazi
# zaidi ya 20" must never turn "wafanyakazi" into a required keyword.
_STRUCTURAL_WORDS = {
    # size vocabulary (Swahili + English)
    "wafanyakazi", "mfanyakazi", "employees", "employee", "staff", "watu", "workers",
    "people", "vibarua", "zaidi", "chini", "kupita", "hadi", "more", "than", "over",
    "under", "below", "above", "less", "fewer", "least", "plus",
    # request scaffolding
    "kampuni", "companies", "company", "leads", "records", "mashirika", "wateja",
    "biashara", "taasisi", "nipe", "nataka", "tafuta", "find", "get", "give", "show",
    "list", "fetch", "top", "me", "please", "tafadhali", "of", "the", "and", "or",
    "with", "having", "zenye", "wenye", "yenye", "ambao", "ambazo", "ambaao",
    "na", "kwa", "ya", "za", "la", "wa", "in", "at", "for", "from", "to", "not",
    "bila", "isipokuwa", "excluding", "without", "except", "hizo", "hawa", "zote",
    "wote", "jina", "yenye", "mkoa", "wilaya", "nchi", "region", "district",
    # quantifiers that survive the connector split
    "mengi", "mingi", "kati", "between", "baada", "kila", "some", "any", "all",
    "being", "that", "which", "who", "their", "they", "have", "has", "had",
}


def _keyword_denylist() -> set[str]:
    """Structural words plus every sector/signal word we already handle elsewhere.

    Sector words are stripped because sector is its own filter: leaving "hoteli"
    in include_keywords would demand the literal token in the company name and
    knock points off perfectly good hotels.
    """
    deny = set(_STRUCTURAL_WORDS)
    for keywords in list(SECTOR_KEYWORDS.values()) + list(SIGNAL_KEYWORDS.values()):
        for kw in keywords:
            deny.update(w for w in str(kw).split() if len(w) > 2)
    # Region/alias tokens: "zenye magari mengi Arusha" must not demand "arusha"
    # inside the company name — the region filter already covers it.
    for region in TANZANIA_REGIONS:
        deny.update(w for w in squash(region).split() if len(w) > 2)
    for alias in REGION_ALIASES:
        deny.update(w for w in squash(alias).split() if len(w) > 2)
    return deny


def _clean_keyword_chunk(chunk: str, deny: set[str]) -> str:
    tokens = [t for t in re.split(r"\s+", chunk.strip()) if t]
    kept = [t for t in tokens if t not in deny and not t.isdigit()]
    return " ".join(kept).strip()


def _find_keywords(text: str) -> tuple[list[str], list[str]]:
    include: list[str] = []
    exclude: list[str] = []
    deny = _keyword_denylist()
    for m in re.finditer(r"(?:with|having|zenye|wenye)\s+([a-z\s&]{3,40})", text):
        chunk = m.group(1).strip()
        chunk = re.split(r"\b(and|na|in|at|with|for|zaidi|ambao)\b", chunk)[0].strip()
        chunk = _clean_keyword_chunk(chunk, deny)
        if 2 < len(chunk) < 40:
            include.append(chunk)
    for m in re.finditer(r"(?:excluding|without|bila|isipokuwa|not)\s+([a-z\s&]{3,40})", text):
        chunk = re.split(r"\b(and|na|in|at|for)\b", m.group(1).strip())[0].strip()
        chunk = _clean_keyword_chunk(chunk, deny)
        if 2 < len(chunk) < 40:
            exclude.append(chunk)
    return include[:4], exclude[:4]


def detect_language(text: str) -> str:
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    sw_hits = len(tokens & _SW_INDICATORS)
    return "Swahili" if sw_hits >= 2 else "English"


def suggest_name(parsed: dict) -> str:
    parts = []
    if parsed.get("sector"):
        parts.append(parsed["sector"].split("&")[0].strip())
    if parsed.get("region"):
        parts.append(parsed["region"])
    if parsed.get("watch_signals"):
        parts.append(parsed["watch_signals"][0])
    if not parts:
        return "Untitled ICP"
    return " · ".join(parts)


def parse_prompt(prompt: str, defaults: dict | None = None) -> dict:
    """Parse a free-text request into ICP fields.

    Returns a dict with keys shaped like the Dalili ICP DocType, plus
    `_confidence` notes explaining what was inferred.
    """
    defaults = defaults or {}
    text = squash(prompt or "")
    # Hyphen-preserving variant for numeric parsing ("20-50 employees").
    numeric_text = re.sub(r"\s+", " ", (prompt or "").lower()).strip()
    notes: list[str] = []

    sector, _ = _find_sector(text)
    if sector:
        notes.append(f"sector inferred as {sector}")

    region = _find_region(text)
    if region:
        notes.append(f"region detected: {region}")
    else:
        region = defaults.get("region")

    count = _find_count(text)
    if count:
        notes.append(f"target count: {count}")

    lo, hi = _find_size(numeric_text)
    if lo or hi:
        notes.append(f"employee bounds: {lo}-{hi}")

    signals = _find_signals(text)
    if signals:
        notes.append(f"signals to watch: {', '.join(signals)}")

    seniority, _ = _find_seniority(text)
    department = _find_department(text)
    include, exclude = _find_keywords(text)
    language = detect_language(prompt or "")

    parsed = {
        "icp_name": suggest_name(
            {"sector": sector, "region": region, "watch_signals": signals}
        ),
        "prompt_text": prompt,
        "sector": sector,
        "region": region,
        "district": None,
        "employee_band_min": lo,
        "employee_band_max": hi,
        "include_keywords": ", ".join(include) if include else None,
        "exclude_keywords": ", ".join(exclude) if exclude else None,
        "watch_signals": signals,
        "target_count": count or defaults.get("target_count") or 50,
        "min_score": defaults.get("min_score") or 60,
        "languages": "Both" if language == "Swahili" else "English",
        "seniority_preference": seniority or "Any",
        "preferred_department": department,
        "_confidence": notes,
        "_language": language,
        "_parsed_fields": {
            "sector": bool(sector),
            "region": bool(region),
            "size": bool(lo or hi),
            "count": bool(count),
            "signals": bool(signals),
        },
    }
    return parsed


def clarifying_questions(parsed: dict, limit: int = 3) -> list[str]:
    """Ask only what actually changes the result set."""
    questions = []
    fields = parsed.get("_parsed_fields") or {}
    if not fields.get("sector"):
        questions.append("Unatafuta sekta gani? (mfano: hoteli, ujenzi, usafirishaji) / Which sector?")
    if not fields.get("region"):
        questions.append("Eneo gani — Dar es Salaam, Arusha, au Tanzania nzima? / Which region?")
    if not fields.get("size"):
        questions.append("Ukubwa wa kampuni — wafanyakazi wangapi? / Company size in employees?")
    if not fields.get("count"):
        questions.append("Unahitaji lead ngapi kwa mkupuo huu? / How many leads this round?")
    return questions[:limit]

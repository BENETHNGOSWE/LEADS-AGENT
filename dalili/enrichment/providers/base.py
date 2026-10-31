"""Provider interface + registry.

A provider is a thin adapter over one data source. The waterfall (see
`dalili/enrichment/waterfall.py`) chains providers; it does not care which one
answered, only that the field is now filled and by whom.

Every provider must degrade gracefully: if it is disabled, unconfigured, or the
network is down, it returns [] / {} rather than raising. A missing API key must
never break an agent run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    records: list[dict] = field(default_factory=list)
    calls: int = 0
    cost: float = 0.0
    error: str = ""

    def ok(self) -> bool:
        return not self.error


class BaseProvider:
    """All providers implement `search` (discovery) and `enrich` (detail fill)."""

    source_name: str = "Base"
    source_type: str = "Manual"

    def __init__(self, **options):
        self.options = options or {}

    # -- discovery ---------------------------------------------------------
    def search(self, filters: dict, limit: int = 50) -> ProviderResult:
        return ProviderResult()

    # -- enrichment --------------------------------------------------------
    def enrich(self, record: dict) -> ProviderResult:
        return ProviderResult()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def to_record(**kwargs) -> dict:
        """Canonical internal record shape."""
        record = {
            "company_name": "",
            "legal_name": "",
            "sector": "",
            "sub_sector": "",
            "region": "",
            "district": "",
            "ward": "",
            "address": "",
            "latitude": None,
            "longitude": None,
            "primary_phone": "",
            "primary_whatsapp": "",
            "primary_email": "",
            "website": "",
            "domain": "",
            "employee_band": "",
            "revenue_band": "",
            "founded_year": None,
            "brela_number": "",
            "tin": "",
            "vat_number": "",
            "source_label": self.source_name if self else "",
            "source_type": self.source_type if self else "",
            "confidence": 60,
            "contacts": [],
            "signals": [],
        }
        record.update(kwargs)
        return record


def load_providers(*, discovery_only=False):
    """Instantiate enabled providers ordered by their Data Source priority."""
    import frappe

    from dalili.enrichment.providers.demo import DemoProvider
    from dalili.enrichment.providers.google_places import GooglePlacesProvider
    from dalili.enrichment.providers.llm import LLMProvider
    from dalili.enrichment.providers.osm import OSMProvider
    from dalili.enrichment.providers.registry import RegistryProvider

    settings = frappe.get_cached_doc("Dalili Settings")
    demo_mode = bool(settings.demo_mode)
    providers: list[BaseProvider] = []

    rows = frappe.get_all(
        "Dalili Data Source",
        filters={"enabled": 1},
        fields=[
            "name", "source_name", "source_type", "priority", "api_key",
            "endpoint", "reliability", "cost_per_call",
        ],
        order_by="priority asc",
    )

    mapping = {
        "Places API": GooglePlacesProvider,
        "Company Registry": RegistryProvider,
        "CSV Upload": RegistryProvider,
        "LLM Research": LLMProvider,
        "Manual": DemoProvider,
        "Open Map Data": OSMProvider,
    }

    for row in rows:
        # Demo rows only run in Demo Mode; real rows never run alongside them.
        if row.source_type == "Manual" and not demo_mode:
            continue
        if row.source_type == "Open Map Data" and demo_mode:
            continue
        cls = mapping.get(row.source_type)
        if not cls:
            continue  # source type not yet supported by an adapter — skip quietly
        if row.source_type == "Places API" and not (row.api_key or settings.google_places_api_key if hasattr(settings, "google_places_api_key") else row.api_key):
            continue
        providers.append(
            cls(
                source_name=row.source_name,
                source_type=row.source_type,
                priority=row.priority,
                reliability=row.reliability,
                cost_per_call=row.cost_per_call,
                endpoint=row.endpoint,
                api_key=row.get_password("api_key") if row.api_key else None,
                settings=settings,
            )
        )

    if discovery_only:
        return [p for p in providers if p.source_type in ("Places API", "Manual", "Company Registry", "CSV Upload", "LLM Research")]
    return providers

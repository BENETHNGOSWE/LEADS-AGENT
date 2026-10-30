"""Optional LLM provider.

Used for two things only:
  1. writing the "why now" sentence for a lead card (judgement, not data);
  2. refining a free-text ICP into filters the rule-based parser missed.

Deliberately NOT used for facts. An LLM will happily invent a phone number, so
phones/emails/addresses always come from a retrieved source, never from a model.
That distinction is the whole credibility of the product.

Works with any OpenAI-compatible endpoint (OpenAI, Azure, Groq, Together, a local
vLLM, etc.) via `Dalili Settings.llm_base_url`.
"""

from __future__ import annotations

import json

from dalili.enrichment.providers.base import BaseProvider, ProviderResult


def _settings():
    try:
        import frappe

        return frappe.get_cached_doc("Dalili Settings")
    except Exception:
        return None


class LLMProvider(BaseProvider):
    source_name = "LLM Research"
    source_type = "LLM Research"

    # ------------------------------------------------------------------
    def _config(self):
        settings = self.options.get("settings") or _settings()
        if not settings:
            return None
        if not getattr(settings, "llm_enabled", 0):
            return None
        key = None
        try:
            key = settings.get_password("llm_api_key", raise_exception=False)
        except Exception:
            key = None
        if not key:
            return None
        return {
            "key": key,
            "base_url": (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/"),
            "model": settings.llm_model or "gpt-4o-mini",
            "timeout": int(settings.llm_timeout or 30),
            "max_tokens": int(settings.llm_max_tokens or 700),
        }

    # ------------------------------------------------------------------
    def _chat(self, messages, *, json_mode=False):
        config = self._config()
        if not config:
            return None
        try:
            import requests
        except ImportError:  # pragma: no cover
            return None

        payload = {
            "model": config["model"],
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": config["max_tokens"],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                f"{config['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config['key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config["timeout"],
            )
            if response.status_code != 200:
                return None
            data = response.json()
            return (data.get("choices") or [{}])[0].get("message", {}).get("content")
        except Exception:
            return None

    # ------------------------------------------------------------------
    def why_now(self, record: dict) -> str:
        """One sentence explaining why this company is worth calling now."""
        signals = record.get("signals") or []
        if not signals and not record.get("sector"):
            return ""

        description = "\n".join(
            f"- {s.get('title')} ({s.get('category')}), detected {s.get('detected_on')}"
            for s in signals[:5]
        ) or "- no recent trigger recorded"

        messages = [
            {
                "role": "system",
                "content": (
                    "You write one short, concrete sentence for a Tanzanian B2B sales "
                    "brief explaining why this company might buy now. Max 22 words. "
                    "No hype, no exclamation marks, no invented facts. If the evidence "
                    "is thin, say what is known and nothing more."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {record.get('company_name')}\n"
                    f"Sector: {record.get('sector')}\n"
                    f"Region: {record.get('region')}\n"
                    f"Signals:\n{description}"
                ),
            },
        ]
        text = self._chat(messages)
        return (text or "").strip().strip('"')[:240]

    # ------------------------------------------------------------------
    def parse_icp(self, prompt: str) -> dict:
        """Return a partial ICP dict, or {} when the LLM is unavailable."""
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract B2B lead-search filters from the user's request (Swahili or "
                    "English). Reply with JSON only, using these keys: sector, region, "
                    "district, employee_band_min, employee_band_max, include_keywords, "
                    "exclude_keywords, target_count, seniority_preference, "
                    "preferred_department, watch_signals (array). "
                    "Use null for anything not stated. Do not invent values."
                ),
            },
            {"role": "user", "content": prompt[:2000]},
        ]
        raw = self._chat(messages, json_mode=True)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # ------------------------------------------------------------------
    def search(self, filters: dict, limit: int = 50) -> ProviderResult:
        """The LLM is not a discovery source. Kept for interface completeness."""
        return ProviderResult()

    def enrich(self, record: dict) -> ProviderResult:
        text = self.why_now(record)
        if not text:
            return ProviderResult()
        return ProviderResult(
            records=[{"why_now": text, "source_label": self.source_name,
                      "source_type": self.source_type, "confidence": 45}],
            calls=1,
            cost=float(self.options.get("cost_per_call") or 0.01),
        )

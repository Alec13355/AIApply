from __future__ import annotations

import json
from typing import Any

from openai import AzureOpenAI

from .config import AzureSettings, load_azure_settings


class AzureAIClient:
    """Thin wrapper around the Azure AI Foundry (Azure OpenAI-compatible) chat endpoint."""

    def __init__(self, settings: AzureSettings | None = None):
        self.settings = settings or load_azure_settings()
        self._client = AzureOpenAI(
            azure_endpoint=self.settings.azure_ai_endpoint,
            api_key=self.settings.azure_ai_key,
            api_version=self.settings.azure_ai_api_version,
        )
        self._deployment = self.settings.azure_ai_deployment

    def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def complete_json(
        self, system: str, user: str, *, temperature: float = 0.2
    ) -> dict[str, Any]:
        """Chat completion constrained to a single JSON object response."""
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

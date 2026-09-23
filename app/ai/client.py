import asyncio
import json

import httpx

from app.ai.prompts import SYSTEM_PROMPT
from app.services.evidence import Evidence


class LLMClient:
    """Chat-completions compatible transport with a whole-call deadline and no retries."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: float = 3.0):
        self._api_key = api_key
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._timeout = min(max(timeout_seconds, 0.05), 5.0)

    def select_reasons(self, evidence: tuple[Evidence, ...]) -> object:
        return asyncio.run(self._select(evidence))

    async def _select(self, evidence: tuple[Evidence, ...]) -> object:
        body = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 600,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"candidates": [item.as_payload() for item in evidence]},
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        async with asyncio.timeout(self._timeout):
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                async with client.stream(
                    "POST",
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                ) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 65536:
                            raise ValueError("AI response exceeds limit")
        content = json.loads(data)["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("AI content is not text")
        return json.loads(content)

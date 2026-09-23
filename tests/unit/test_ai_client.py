import asyncio
import json
from time import monotonic

import httpx
import pytest

from app.ai.client import LLMClient
from app.models import RecommendationRequest
from app.services.evidence import build_evidence
from app.services.explanation import ExplanationService, render_explanation


@pytest.fixture
def evidence(profile, payload):
    return (build_evidence(profile, RecommendationRequest.from_payload(payload)),)


def transport(monkeypatch, handler):
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        "app.ai.client.httpx.AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_transport_request_and_response(monkeypatch, evidence):
    captured = []
    selected = {
        "items": [
            {
                "candidate_id": evidence[0].candidate_id,
                "reason_id": evidence[0].semantic_reasons[-1].reason_id,
            }
        ]
    }

    def handler(request):
        captured.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(selected)}}]}
        )

    transport(monkeypatch, handler)
    client = LLMClient("test-runtime-token", "https://provider.example/v1", "test-model")
    assert client.select_reasons(evidence) == selected
    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "https://provider.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-runtime-token"
    body = json.loads(request.content)
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert json.loads(body["messages"][1]["content"]) == {
        "candidates": [json.loads(json.dumps(evidence[0].as_payload()))]
    }
    assert "test-runtime-token" not in request.content.decode()


@pytest.mark.parametrize(
    "status,body",
    [
        (500, b"private provider detail"),
        (401, b"private provider detail"),
        (200, b"not json"),
        (200, b"{}"),
        (200, b'{"choices":[]}'),
        (200, b'{"choices":[{"message":{"content":null}}]}'),
        (200, b'{"choices":[{"message":{"content":"not json"}}]}'),
        (200, b"x" * 65537),
    ],
    ids=[
        "server-error",
        "unauthorized",
        "invalid-json",
        "missing-choices",
        "empty-choices",
        "null-content",
        "invalid-content",
        "oversized",
    ],
)
def test_transport_errors_fall_back_without_leak(monkeypatch, evidence, status, body, caplog):
    transport(monkeypatch, lambda request: httpx.Response(status, content=body))
    service = ExplanationService(
        LLMClient("test-runtime-token", "https://provider.example/v1", "test-model")
    )
    result = service.explain(evidence)
    assert result == {evidence[0].candidate_id: render_explanation(evidence[0])}
    assert "test-runtime-token" not in str(result) + caplog.text
    assert "private provider detail" not in str(result) + caplog.text


def test_transport_does_not_follow_redirects(monkeypatch, evidence):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://untrusted.example"})

    transport(monkeypatch, handler)
    ExplanationService(
        LLMClient("test-runtime-token", "https://provider.example/v1", "test-model")
    ).explain(evidence)
    assert calls == ["https://provider.example/v1/chat/completions"]


@pytest.mark.parametrize("stall_body", [False, True])
def test_whole_call_deadline_and_stream_cancellation(monkeypatch, evidence, stall_body):
    closed = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"
            await asyncio.sleep(30)
            yield b"}"

        async def aclose(self):
            closed.append(True)

    async def handler(request):
        if not stall_body:
            await asyncio.sleep(30)
        return httpx.Response(200, stream=SlowBody())

    transport(monkeypatch, handler)
    start = monotonic()
    client = LLMClient(
        "test-runtime-token", "https://provider.example/v1", "test-model", timeout_seconds=0.05
    )
    result = ExplanationService(client).explain(evidence)
    assert monotonic() - start < 1
    assert result == {evidence[0].candidate_id: render_explanation(evidence[0])}
    if stall_body:
        assert closed == [True]

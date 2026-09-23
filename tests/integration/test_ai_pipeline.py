from app import create_app


class Provider:
    def __init__(self, fail=False):
        self.received = None
        self.fail = fail

    def select_reasons(self, evidence):
        self.received = evidence
        if self.fail:
            raise RuntimeError("provider-private-error")
        return {
            "items": [
                {
                    "candidate_id": item.candidate_id,
                    "reason_id": item.semantic_reasons[-1].reason_id,
                }
                for item in evidence
            ]
        }


def test_api_ai_success_and_failure_share_order_and_schema(repository, payload):
    successful = Provider()
    failed = Provider(fail=True)
    config = {"TESTING": True, "LLM_API_KEY": ""}
    answers = []
    for provider in (successful, failed):
        client = create_app(config, repository=repository, ai_client=provider).test_client()
        response = client.post("/api/v1/recommendations", json=payload)
        assert response.status_code == 200
        assert "provider-private-error" not in response.text
        answers.append(response.json)
    assert [card["id"] for card in answers[0]["recommendations"]] == [
        card["id"] for card in answers[1]["recommendations"]
    ]
    assert (
        successful.received[0].semantic_reasons[-1].source_text
        in answers[0]["recommendations"][0]["explanation"]
    )
    assert (
        failed.received[0].semantic_reasons[0].source_text
        in answers[1]["recommendations"][0]["explanation"]
    )


def test_runtime_environment_is_read_at_app_creation(monkeypatch, repository):
    monkeypatch.setenv("LLM_API_KEY", "test-runtime-token")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    app = create_app({"TESTING": True}, repository=repository)
    assert app.extensions["recommendation_service"].explanations.client is not None
    monkeypatch.delenv("LLM_API_KEY")
    app = create_app({"TESTING": True}, repository=repository)
    assert app.extensions["recommendation_service"].explanations.client is None

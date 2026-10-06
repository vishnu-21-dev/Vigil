from __future__ import annotations

import importlib
import json
import logging
from types import SimpleNamespace

import pytest

from api import config, groq_client
from api.store import get_report


API_KEY = "gsk_test_secret_key_123"
ALERT = {"id": "a1", "alert_type": "Anomaly Detected", "confidence": 0.97}
DEVICE = {"id": "d1", "name": "PLC Controller", "ip_address": "10.0.10.5", "zone": "Production Floor"}


def _completion(payload: dict):
    message = SimpleNamespace(content=json.dumps(payload))
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture
def fake_groq(monkeypatch):
    """Replace groq.Groq with a fake and give the client module a key and model."""
    monkeypatch.setattr(
        groq_client, "settings", SimpleNamespace(groq_api_key=API_KEY, groq_model="test-model")
    )
    state = SimpleNamespace(init_kwargs=None, create_kwargs=None, respond=None)

    class FakeGroq:
        def __init__(self, **kwargs):
            state.init_kwargs = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            state.create_kwargs = kwargs
            return state.respond()

    monkeypatch.setattr("groq.Groq", FakeGroq)
    return state


@pytest.fixture
def server_log(caplog):
    """Capture the logger the app writes to, regardless of uvicorn's propagation setup."""
    logger = logging.getLogger("uvicorn.error")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    yield caplog
    logger.removeHandler(caplog.handler)


def _warnings(caplog) -> str:
    return " | ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)


def test_failing_groq_call_falls_back_and_logs_a_warning(fake_groq, server_log):
    def boom():
        raise RuntimeError("Error code: 400 - model_decommissioned")

    fake_groq.respond = boom

    report = groq_client.generate_incident_report(ALERT, DEVICE)

    assert report == {**groq_client._fallback_report(ALERT, DEVICE), "source": "fallback"}
    logged = _warnings(server_log)
    assert "RuntimeError" in logged, f"exception type missing from log: {logged!r}"
    assert "model_decommissioned" in logged, f"exception message missing from log: {logged!r}"


def test_warning_never_contains_the_api_key(fake_groq, server_log):
    def boom():
        raise RuntimeError(f"401 unauthorized for key {API_KEY}")

    fake_groq.respond = boom

    groq_client.generate_incident_report(ALERT, DEVICE)

    logged = _warnings(server_log)
    assert logged, "no warning was logged"
    assert API_KEY not in logged


def test_client_uses_short_timeout_no_retries_and_the_configured_model(fake_groq):
    fake_groq.respond = lambda: _completion(
        {"title": "LLM title", "severity": "high", "summary": "S", "full_report": "F"}
    )

    report = groq_client.generate_incident_report(ALERT, DEVICE)

    assert report["title"] == "LLM title"
    assert report["source"] == "llm"
    assert fake_groq.init_kwargs == {"api_key": API_KEY, "timeout": 10.0, "max_retries": 0}
    assert fake_groq.create_kwargs["model"] == "test-model"


def _reload_config(monkeypatch, groq_model):
    if groq_model is None:
        monkeypatch.delenv("GROQ_MODEL", raising=False)
    else:
        monkeypatch.setenv("GROQ_MODEL", groq_model)
    return importlib.reload(config)


def test_groq_model_defaults_to_llama_3_1_8b_instant(monkeypatch):
    try:
        assert _reload_config(monkeypatch, None).settings.groq_model == "openai/gpt-oss-20b"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_groq_model_env_var_is_respected(monkeypatch):
    try:
        assert _reload_config(monkeypatch, "some-other-model").settings.groq_model == "some-other-model"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_no_api_key_returns_the_fallback_marked_as_such(monkeypatch):
    monkeypatch.setattr(groq_client, "settings", SimpleNamespace(groq_api_key="", groq_model="m"))

    report = groq_client.generate_incident_report(ALERT, DEVICE)

    assert report == {**groq_client._fallback_report(ALERT, DEVICE), "source": "fallback"}


def _generate_report_via_api(client):
    alert_id = client.post("/demo/trigger-anomaly").json()["alert_id"]
    response = client.post("/reports/generate", json={"alert_id": alert_id})
    assert response.status_code == 200
    return response.json()


def test_stored_report_records_llm_source_but_api_shape_is_unchanged(client, fake_groq):
    fake_groq.respond = lambda: _completion(
        {"title": "LLM title", "severity": "high", "summary": "S", "full_report": "F"}
    )

    body = _generate_report_via_api(client)

    assert get_report(body["id"])["source"] == "llm"
    assert "source" not in body  # ReportResponse is unchanged


def test_stored_report_records_fallback_source_when_groq_fails(client, fake_groq):
    def boom():
        raise RuntimeError("model_decommissioned")

    fake_groq.respond = boom

    body = _generate_report_via_api(client)

    assert get_report(body["id"])["source"] == "fallback"
    assert "source" not in body

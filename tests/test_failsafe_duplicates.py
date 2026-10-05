from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api import failsafe, groq_client
from api.store import add_alert


CLOCK_JUMP_SECONDS = failsafe.FAILSAFE_TIMEOUT + 80


class _StopLoop(Exception):
    pass


class _FutureDatetime(datetime):
    """datetime whose now() is shifted past the failsafe timeout."""

    jump_seconds = CLOCK_JUMP_SECONDS

    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) + timedelta(seconds=cls.jump_seconds)


@pytest.fixture(autouse=True)
def _stub_inference(monkeypatch):
    """Always report a high-confidence anomaly; the model and dataset are not under test."""
    monkeypatch.setattr(
        "api.routers.monitor.run_inference",
        lambda _features: {"label": 1, "confidence": 0.97, "is_anomaly": True},
    )


@contextmanager
def _patched_failsafe(
    jump_seconds: int = CLOCK_JUMP_SECONDS, ticks: int = 1, real_to_thread: bool = False
):
    """Patch failsafe's own asyncio/datetime references (the app's live loop is untouched).

    sleep returns immediately and stops the loop after `ticks` ticks; the clock is shifted
    forward; to_thread runs the function inline unless real_to_thread is set.
    """
    sleeps = 0
    shifted = type("_Shifted", (_FutureDatetime,), {"jump_seconds": jump_seconds})

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > ticks:
            raise _StopLoop

    async def inline_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    fake_asyncio = SimpleNamespace(
        sleep=fake_sleep,
        to_thread=asyncio.to_thread if real_to_thread else inline_to_thread,
    )
    with patch.object(failsafe, "asyncio", fake_asyncio), patch.object(
        failsafe, "datetime", shifted
    ):
        yield


def _run_one_failsafe_tick(jump_seconds: int = CLOCK_JUMP_SECONDS, ticks: int = 1) -> None:
    """Run failsafe_loop through `ticks` ticks, with the clock jumped forward."""
    with _patched_failsafe(jump_seconds, ticks):
        with pytest.raises(_StopLoop):
            asyncio.run(failsafe.failsafe_loop())


def _ingest_anomaly(client) -> tuple[dict, dict]:
    device = client.get("/devices/").json()[0]
    response = client.post(
        "/monitor/ingest",
        json={"device_id": device["id"], "features": {}},
    )
    assert response.status_code == 200
    ingest = response.json()
    assert ingest["is_anomaly"] is True
    assert ingest["confidence"] >= failsafe.FAILSAFE_THRESHOLD
    return device, ingest


def _requests_for(client, device_id: str) -> list[dict]:
    return [r for r in client.get("/quarantine/").json() if r["device_id"] == device_id]


def test_failsafe_after_timeout_leaves_exactly_one_quarantine_request(client):
    device, _ = _ingest_anomaly(client)

    _run_one_failsafe_tick()

    requests = _requests_for(client, device["id"])
    assert len(requests) == 1, (
        f"expected 1 quarantine request, found {len(requests)}: "
        f"{[r['status'] for r in requests]}"
    )
    assert requests[0]["status"] == "ai_contained"


def test_failsafe_does_not_act_after_human_approval(client):
    device, ingest = _ingest_anomaly(client)

    approve = client.post(
        f"/quarantine/{ingest['quarantine_request_id']}/approve",
        json={"approved_by": "pytest"},
    )
    assert approve.status_code == 200
    assert client.get(f"/devices/{device['id']}").json()["status"] == "quarantined"

    _run_one_failsafe_tick()

    requests = _requests_for(client, device["id"])
    assert [r["status"] for r in requests] == ["approved"], (
        f"failsafe added or changed requests: {[r['status'] for r in requests]}"
    )
    assert client.get("/reports/").json() == [], "failsafe generated a report after human approval"


def test_containment_stands_when_report_generation_fails(client):
    device, _ = _ingest_anomaly(client)

    def boom(*_args, **_kwargs):
        raise RuntimeError("report backend down")

    with patch.object(failsafe, "generate_incident_report", boom):
        _run_one_failsafe_tick()

    assert client.get(f"/devices/{device['id']}").json()["status"] == "quarantined"
    requests = _requests_for(client, device["id"])
    assert [r["status"] for r in requests] == ["ai_contained"]
    assert all(a["acknowledged"] for a in client.get("/alerts/").json())
    assert client.get("/reports/").json() == []


def test_demo_and_ingest_alerts_are_both_contained_after_timeout(client):
    """Regression guard: created_at written by the demo endpoint (datetime) and by
    add_alert's setdefault (ISO string) must both be parsed by the failsafe."""
    devices = client.get("/devices/").json()
    demo = client.post("/demo/trigger-anomaly")
    assert demo.status_code == 200
    demo_alert = client.get(f"/alerts/{demo.json()['alert_id']}").json()

    # The demo endpoint picks the first non-quarantined device, so ingest on a different one.
    ingest_device = next(d for d in devices if d["id"] != demo_alert["device_id"])
    ingest = client.post(
        "/monitor/ingest", json={"device_id": ingest_device["id"], "features": {}}
    ).json()
    ingest_alert = client.get(f"/alerts/{ingest['alert_id']}").json()
    assert demo_alert["device_id"] != ingest_alert["device_id"]

    _run_one_failsafe_tick(jump_seconds=121)

    for label, alert in (("demo", demo_alert), ("ingest", ingest_alert)):
        device_requests = _requests_for(client, alert["device_id"])
        assert [r["status"] for r in device_requests] == ["ai_contained"], label
        assert client.get(f"/devices/{alert['device_id']}").json()["status"] == "quarantined", label
        assert client.get(f"/alerts/{alert['id']}").json()["acknowledged"] is True, label


def test_one_unparseable_alert_does_not_stop_the_failsafe(client):
    devices = client.get("/devices/").json()
    valid_device, bad_device = devices[0], devices[2]
    ingest = client.post(
        "/monitor/ingest", json={"device_id": valid_device["id"], "features": {}}
    ).json()

    # Sorts before the valid alert so the loop reaches it first.
    add_alert(
        {
            "id": "bad-created-at",
            "device_id": bad_device["id"],
            "device_name": bad_device["name"],
            "alert_type": "Anomaly Detected",
            "confidence": 0.97,
            "timestamp": "2026-10-05T00:00:00+00:00",
            "zone": bad_device["zone"],
            "status": "active",
            "created_at": "1970-garbage",
        }
    )

    _run_one_failsafe_tick()  # must not raise

    assert client.get(f"/alerts/{ingest['alert_id']}").json()["acknowledged"] is True
    assert [r["status"] for r in _requests_for(client, valid_device["id"])] == ["ai_contained"]
    assert client.get(f"/devices/{valid_device['id']}").json()["status"] == "quarantined"


def test_failure_fetching_alerts_does_not_end_the_loop(client):
    device, ingest = _ingest_anomaly(client)
    real_fetch = failsafe.get_active_unacknowledged_alerts
    calls = 0

    def flaky_fetch():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db temporarily unavailable")
        return real_fetch()

    with patch.object(failsafe, "get_active_unacknowledged_alerts", flaky_fetch):
        _run_one_failsafe_tick(ticks=2)  # must not raise

    assert calls == 2
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["ai_contained"]


def test_failing_fetch_still_waits_one_interval_per_attempt(client):
    """The error path must not skip the sleep (no tight retry loop)."""
    events: list[str] = []

    def always_failing_fetch():
        events.append("fetch")
        raise RuntimeError("db down")

    async def recording_sleep(_seconds):
        events.append("sleep")
        if events.count("sleep") > 3:
            raise _StopLoop

    with patch.object(failsafe, "asyncio", SimpleNamespace(sleep=recording_sleep)), patch.object(
        failsafe, "get_active_unacknowledged_alerts", always_failing_fetch
    ):
        with pytest.raises(_StopLoop):
            asyncio.run(failsafe.failsafe_loop())

    assert events == ["sleep", "fetch", "sleep", "fetch", "sleep", "fetch", "sleep"]


def test_resolving_an_ai_contained_alert_leaves_containment_intact(client):
    device, ingest = _ingest_anomaly(client)
    _run_one_failsafe_tick()
    assert client.get(f"/devices/{device['id']}").json()["status"] == "quarantined"

    response = client.post(f"/alerts/{ingest['alert_id']}/resolve")

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert client.get(f"/devices/{device['id']}").json()["status"] == "quarantined"
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["ai_contained"]


def test_resolving_an_alert_on_an_anomaly_device_still_resets_it_to_normal(client):
    device, ingest = _ingest_anomaly(client)
    assert client.get(f"/devices/{device['id']}").json()["status"] == "anomaly"

    response = client.post(f"/alerts/{ingest['alert_id']}/resolve")

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    updated = client.get(f"/devices/{device['id']}").json()
    assert updated["status"] == "normal"
    assert updated["anomaly_score"] == 0.0


def test_slow_report_does_not_block_the_event_loop(client, monkeypatch):
    """A 3s blocking Groq call inside auto_quarantine must not freeze other async work."""
    monkeypatch.setattr(
        groq_client, "settings", SimpleNamespace(groq_api_key="test-key", groq_model="test-model")
    )

    def slow_create(**_kwargs):
        time.sleep(3)  # blocking, like the real synchronous SDK call
        payload = {"title": "T", "severity": "high", "summary": "S", "full_report": "F"}
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class SlowGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=slow_create))

    monkeypatch.setattr("groq.Groq", SlowGroq)
    device, _ = _ingest_anomaly(client)

    real_sleep = asyncio.sleep
    beats: list[float] = []

    async def scenario():
        async def heartbeat():
            while True:
                await real_sleep(0.1)
                beats.append(time.monotonic())

        task = asyncio.create_task(heartbeat())
        await real_sleep(0.3)  # let the heartbeat start
        started = time.monotonic()
        try:
            await failsafe.failsafe_loop()
        except _StopLoop:
            pass
        finished = time.monotonic()
        task.cancel()
        return started, finished

    with _patched_failsafe(real_to_thread=True):
        started, finished = asyncio.run(scenario())

    during = [started] + [b for b in beats if started <= b <= finished] + [finished]
    longest_stall = max(b - a for a, b in zip(during, during[1:]))

    assert finished - started >= 2.5, "the slow report never ran inside the tick"
    assert client.get(f"/devices/{device['id']}").json()["status"] == "quarantined"
    assert longest_stall < 1.0, (
        f"event loop stalled for {longest_stall:.1f}s while the report was generated "
        f"({len(during) - 2} heartbeats in {finished - started:.1f}s)"
    )


def test_human_cannot_approve_or_dismiss_an_ai_contained_request_mid_report(client, monkeypatch):
    """While the failsafe's report is still being generated, the request is already
    ai_contained and the device quarantined. Only release may take it from there."""
    monkeypatch.setattr(
        groq_client, "settings", SimpleNamespace(groq_api_key="test-key", groq_model="test-model")
    )
    report_finished = threading.Event()

    def slow_create(**_kwargs):
        time.sleep(3)
        report_finished.set()
        payload = {"title": "T", "severity": "high", "summary": "S", "full_report": "F"}
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class SlowGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=slow_create))

    monkeypatch.setattr("groq.Groq", SlowGroq)
    device, _ = _ingest_anomaly(client)
    observed: dict = {}

    async def scenario():
        async def human():
            request = None
            for _ in range(200):  # wait for the failsafe to write ai_contained
                found = await asyncio.to_thread(_requests_for, client, device["id"])
                request = next((r for r in found if r["status"] == "ai_contained"), None)
                if request:
                    break
                await asyncio.sleep(0.05)
            assert request, "failsafe never produced an ai_contained request"
            observed["report_still_running"] = not report_finished.is_set()
            observed["dismiss"] = await asyncio.to_thread(
                client.post, f"/quarantine/{request['id']}/dismiss"
            )
            observed["device_after_dismiss"] = (
                await asyncio.to_thread(client.get, f"/devices/{device['id']}")
            ).json()["status"]
            observed["approve"] = await asyncio.to_thread(
                client.post, f"/quarantine/{request['id']}/approve", json={"approved_by": "human"}
            )
            observed["request_id"] = request["id"]

        task = asyncio.create_task(human())
        try:
            await failsafe.failsafe_loop()
        except _StopLoop:
            pass
        await task

    with _patched_failsafe(real_to_thread=True):
        asyncio.run(scenario())

    assert observed["report_still_running"], "test did not catch the mid-report window"
    after = _requests_for(client, device["id"])
    device_after = client.get(f"/devices/{device['id']}").json()
    detail = (
        f"dismiss={observed['dismiss'].status_code} (device right after dismiss: "
        f"{observed['device_after_dismiss']}), approve={observed['approve'].status_code}, "
        f"request now {[r['status'] for r in after]}, device now {device_after['status']}"
    )
    assert observed["dismiss"].status_code == 400, detail
    assert observed["approve"].status_code == 400, detail
    assert [r["status"] for r in after] == ["ai_contained"], detail
    assert device_after["status"] == "quarantined", detail

    # Release remains the one way out.
    release = client.post(f"/quarantine/{observed['request_id']}/release")
    assert release.status_code == 200
    assert client.get(f"/devices/{device['id']}").json()["status"] == "normal"

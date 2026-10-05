from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api import failsafe
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


def _run_one_failsafe_tick(jump_seconds: int = CLOCK_JUMP_SECONDS, ticks: int = 1) -> None:
    """Run failsafe_loop through `ticks` ticks, with the clock jumped forward."""
    sleeps = 0
    shifted = type("_Shifted", (_FutureDatetime,), {"jump_seconds": jump_seconds})

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > ticks:
            raise _StopLoop

    # Patch only failsafe's own references so the app's live loop task is untouched.
    with patch.object(failsafe, "asyncio", SimpleNamespace(sleep=fake_sleep)), patch.object(
        failsafe, "datetime", shifted
    ):
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

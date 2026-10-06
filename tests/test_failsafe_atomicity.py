"""Containment is atomic, serialized against human decisions, and safe across restarts."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import failsafe
from api.main import app
from api.routers import quarantine as quarantine_router
from api.store import get_alert, get_all_reports, update_alert, update_device

from test_failsafe_duplicates import (  # noqa: F401  (_stub_inference is an autouse fixture)
    _ingest_anomaly,
    _requests_for,
    _run_one_failsafe_tick,
    _stub_inference,
)


def _device_status(client, device_id: str) -> str:
    return client.get(f"/devices/{device_id}").json()["status"]


def _alert_for(client, alert_id: str) -> dict:
    return client.get(f"/alerts/{alert_id}").json()


def _make_overdue(alert_id: str, seconds: int = 600) -> None:
    created = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    update_alert(alert_id, {"created_at": created.isoformat()})


# ---- crash window -------------------------------------------------------------


def test_crash_mid_containment_rolls_back_and_the_next_tick_retries(client):
    device, ingest = _ingest_anomaly(client)
    real_update_device = failsafe.update_device

    def crash(*_args, **_kwargs):
        raise RuntimeError("process died mid-containment")

    with patch.object(failsafe, "update_device", crash):
        _run_one_failsafe_tick()  # the loop logs the error and carries on

    # Nothing half-written: the alert was not acknowledged without containment.
    assert _alert_for(client, ingest["alert_id"])["acknowledged"] is False
    assert _device_status(client, device["id"]) == "anomaly"
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["pending"]

    assert failsafe.update_device is real_update_device
    _run_one_failsafe_tick()

    assert _alert_for(client, ingest["alert_id"])["acknowledged"] is True
    assert _device_status(client, device["id"]) == "quarantined"
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["ai_contained"]


def test_report_lost_after_containment_is_backfilled_once(client):
    device, ingest = _ingest_anomaly(client)

    def boom(*_args, **_kwargs):
        raise RuntimeError("process died before the report was stored")

    with patch.object(failsafe, "generate_incident_report", boom):
        _run_one_failsafe_tick()
    assert _device_status(client, device["id"]) == "quarantined"
    assert get_all_reports() == []

    assert failsafe.backfill_missing_reports() == 1
    reports = get_all_reports()
    assert [r["alert_id"] for r in reports] == [ingest["alert_id"]]

    assert failsafe.backfill_missing_reports() == 0
    assert len(get_all_reports()) == 1


# ---- check-then-act race --------------------------------------------------------


def _hold_inside(module, name: str):
    """Patch module.<name> so the first call blocks, still inside its transaction."""
    entered, release = threading.Event(), threading.Event()
    real = getattr(module, name)

    def held(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(10), "test never released the held transaction"
        return real(*args, **kwargs)

    return patch.object(module, name, held), entered, release


def _alert_snapshot(alert_id: str) -> dict:
    alert = get_alert(alert_id)
    assert alert is not None
    return alert


def test_dismiss_waits_for_an_in_flight_containment_then_is_refused(client):
    device, ingest = _ingest_anomaly(client)
    alert = _alert_snapshot(ingest["alert_id"])
    patcher, entered, release = _hold_inside(failsafe, "update_device")
    results: dict = {}

    with patcher:
        contain = threading.Thread(target=failsafe.auto_quarantine, args=(alert, 200.0, 0.97))
        contain.start()
        assert entered.wait(10), "failsafe never reached its write"

        dismiss = threading.Thread(
            target=lambda: results.setdefault(
                "dismiss", client.post(f"/quarantine/{ingest['quarantine_request_id']}/dismiss")
            )
        )
        dismiss.start()
        time.sleep(0.5)
        assert "dismiss" not in results, "dismiss ran while the failsafe held the lock"

        release.set()
        contain.join(10)
        dismiss.join(10)

    assert results["dismiss"].status_code == 400
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["ai_contained"]
    assert _device_status(client, device["id"]) == "quarantined"


def test_failsafe_waits_for_an_in_flight_dismiss_then_does_nothing(client):
    device, ingest = _ingest_anomaly(client)
    alert = _alert_snapshot(ingest["alert_id"])  # the tick's now-stale snapshot
    patcher, entered, release = _hold_inside(quarantine_router, "update_device")
    results: dict = {}

    with patcher:
        dismiss = threading.Thread(
            target=lambda: results.setdefault(
                "dismiss", client.post(f"/quarantine/{ingest['quarantine_request_id']}/dismiss")
            )
        )
        dismiss.start()
        assert entered.wait(10), "dismiss never reached its write"

        contain = threading.Thread(target=failsafe.auto_quarantine, args=(alert, 200.0, 0.97))
        contain.start()
        time.sleep(0.5)
        assert contain.is_alive(), "failsafe ran while the dismiss held the lock"

        release.set()
        dismiss.join(10)
        contain.join(10)

    assert results["dismiss"].status_code == 200
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["dismissed"]
    assert _device_status(client, device["id"]) == "normal"
    assert get_all_reports() == []


@pytest.mark.parametrize("round_", range(15))
def test_racing_dismiss_and_failsafe_always_end_consistent(client, round_):
    """No coordination: whichever wins, the end state must agree with the HTTP answer."""
    device, ingest = _ingest_anomaly(client)
    alert = _alert_snapshot(ingest["alert_id"])
    start = threading.Barrier(2)
    results: dict = {}

    def human():
        start.wait()
        results["dismiss"] = client.post(f"/quarantine/{ingest['quarantine_request_id']}/dismiss")

    def machine():
        start.wait()
        failsafe.auto_quarantine(alert, 200.0, 0.97)

    threads = [threading.Thread(target=human), threading.Thread(target=machine)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)

    statuses = [r["status"] for r in _requests_for(client, device["id"])]
    device_status = _device_status(client, device["id"])
    if results["dismiss"].status_code == 200:
        assert statuses == ["dismissed"] and device_status == "normal", (statuses, device_status)
    else:
        assert results["dismiss"].status_code == 400
        assert statuses == ["ai_contained"] and device_status == "quarantined", (statuses, device_status)


# ---- restart burst ---------------------------------------------------------------


def test_restart_gives_overdue_alerts_one_fresh_window(client):
    device, ingest = _ingest_anomaly(client)
    _make_overdue(ingest["alert_id"])

    with TestClient(app):  # a server restart: lifespan runs again
        pass

    deadline = datetime.fromisoformat(_alert_for(client, ingest["alert_id"])["failsafe_deadline"])
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    assert failsafe.FAILSAFE_TIMEOUT - 10 < remaining <= failsafe.FAILSAFE_TIMEOUT

    _run_one_failsafe_tick(jump_seconds=0)  # first tick after restart
    assert _device_status(client, device["id"]) == "anomaly", "contained without a fresh window"

    _run_one_failsafe_tick(jump_seconds=failsafe.FAILSAFE_TIMEOUT + 5)
    assert _device_status(client, device["id"]) == "quarantined"


def test_restart_grace_is_granted_only_once_per_alert(client):
    _, ingest = _ingest_anomaly(client)
    _make_overdue(ingest["alert_id"])
    assert failsafe.grant_restart_grace() == 1

    _make_overdue(ingest["alert_id"], seconds=10_000)
    update_alert(ingest["alert_id"], {"failsafe_grace_until": (
        datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    assert failsafe.grant_restart_grace() == 0  # a crash loop cannot postpone it forever


def test_restart_leaves_alerts_that_are_not_yet_due_alone(client):
    _, ingest = _ingest_anomaly(client)
    before = _alert_for(client, ingest["alert_id"])["failsafe_deadline"]
    assert failsafe.grant_restart_grace() == 0
    assert _alert_for(client, ingest["alert_id"])["failsafe_deadline"] == before


# ---- ingest must not undo containment --------------------------------------------


def test_benign_reading_does_not_release_a_quarantined_device(client, monkeypatch):
    device, ingest = _ingest_anomaly(client)
    approve = client.post(
        f"/quarantine/{ingest['quarantine_request_id']}/approve", json={"approved_by": "pytest"}
    )
    assert approve.status_code == 200

    monkeypatch.setattr(
        "api.routers.monitor.run_inference",
        lambda _features: {"label": 0, "confidence": 0.99, "is_anomaly": False},
    )
    response = client.post("/monitor/ingest", json={"device_id": device["id"], "features": {}})

    assert response.status_code == 200
    assert response.json()["quarantined"] is True
    assert _device_status(client, device["id"]) == "quarantined"
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["approved"]


def test_anomalous_reading_on_a_quarantined_device_opens_nothing_new(client):
    device, ingest = _ingest_anomaly(client)
    _run_one_failsafe_tick()
    alerts_before = len(client.get("/alerts/").json())

    response = client.post("/monitor/ingest", json={"device_id": device["id"], "features": {}})

    assert response.status_code == 200
    assert "alert_id" not in response.json()
    assert len(client.get("/alerts/").json()) == alerts_before
    assert [r["status"] for r in _requests_for(client, device["id"])] == ["ai_contained"]


def test_repeated_anomalies_share_one_request_and_containment_handles_every_alert(client):
    device, first = _ingest_anomaly(client)
    second = client.post("/monitor/ingest", json={"device_id": device["id"], "features": {}}).json()
    assert second["quarantine_request_id"] == first["quarantine_request_id"]

    _run_one_failsafe_tick()

    assert [r["status"] for r in _requests_for(client, device["id"])] == ["ai_contained"]
    for alert_id in (first["alert_id"], second["alert_id"]):
        assert _alert_for(client, alert_id)["acknowledged"] is True


def test_demo_trigger_never_flips_a_quarantined_device(client):
    devices = client.get("/devices/").json()
    for d in devices:
        update_device(d["id"], {"status": "quarantined"})

    response = client.post("/demo/trigger-anomaly")

    assert response.status_code == 404
    assert all(_device_status(client, d["id"]) == "quarantined" for d in devices)

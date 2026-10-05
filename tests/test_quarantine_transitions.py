from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.store import add_alert, add_quarantine_request, update_device


def _seed_request(client, status: str) -> dict:
    """A request in `status`, its device in the matching state, and one active alert."""
    device = client.get("/devices/").json()[0]
    contained = status in {"approved", "ai_contained"}
    update_device(
        device["id"],
        {"status": "quarantined" if contained else "normal", "anomaly_score": 0.97 if contained else 0.0},
    )
    now = datetime.now(timezone.utc)
    request = {
        "id": str(uuid4()),
        "device_id": device["id"],
        "device_name": device["name"],
        "zone": device["zone"],
        "confidence": 0.97,
        "flagged_at": now,
        "status": status,
        "approved_by": None,
        "approved_at": None,
        "reason": "seeded for test",
        "requires_human_approval": True,
    }
    if status == "ai_contained":
        request.update(triggered_by="AI_FAILSAFE", auto_contained_at=now, approved_by="AI Failsafe")
    add_quarantine_request(request)
    add_alert(
        {
            "id": str(uuid4()),
            "device_id": device["id"],
            "device_name": device["name"],
            "alert_type": "Anomaly Detected",
            "confidence": 0.97,
            "timestamp": now,
            "zone": device["zone"],
            "status": "active",
        }
    )
    return request


def _snapshot(client, request: dict) -> dict:
    return {
        "request": client.get(f"/quarantine/{request['id']}").json(),
        "device": client.get(f"/devices/{request['device_id']}").json(),
        "alerts": client.get("/alerts/").json(),
    }


def _call(client, action: str, request_id: str):
    if action == "approve":
        return client.post(f"/quarantine/{request_id}/approve", json={"approved_by": "human"})
    return client.post(f"/quarantine/{request_id}/dismiss")


@pytest.mark.parametrize("action", ["approve", "dismiss"])
@pytest.mark.parametrize("status", ["approved", "dismissed", "released", "ai_contained"])
def test_approve_and_dismiss_reject_non_pending_requests_and_change_nothing(client, status, action):
    request = _seed_request(client, status)
    before = _snapshot(client, request)

    response = _call(client, action, request["id"])

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    if status == "ai_contained":
        assert detail == "AI-contained requests can only be released."
    else:
        assert status in detail
    assert _snapshot(client, request) == before


def _pending_request_for_a_demo_alert(client) -> dict:
    alert_id = client.post("/demo/trigger-anomaly").json()["alert_id"]
    device_id = client.get(f"/alerts/{alert_id}").json()["device_id"]
    response = client.post("/quarantine/request", json={"device_id": device_id, "reason": "pending test"})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    return response.json()


def test_pending_request_can_still_be_approved(client):
    pending = _pending_request_for_a_demo_alert(client)

    response = _call(client, "approve", pending["id"])

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert client.get(f"/devices/{pending['device_id']}").json()["status"] == "quarantined"


def test_pending_request_can_still_be_dismissed(client):
    pending = _pending_request_for_a_demo_alert(client)

    response = _call(client, "dismiss", pending["id"])

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert client.get(f"/devices/{pending['device_id']}").json()["status"] == "normal"


def test_release_still_works_on_approved_and_ai_contained_requests(client):
    for status in ("approved", "ai_contained"):
        request = _seed_request(client, status)
        response = client.post(f"/quarantine/{request['id']}/release")
        assert response.status_code == 200, status
        assert response.json()["status"] == "released"

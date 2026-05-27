from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]


def _sample_features(name: str) -> dict[str, float]:
    return pd.read_csv(ROOT_DIR / "data" / name, nrows=1).iloc[0].to_dict()


def test_health_and_seeded_inventory(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "0.1.0"}

    devices = client.get("/devices/")
    assert devices.status_code == 200
    assert len(devices.json()) == 5

    zones = client.get("/zones/")
    assert zones.status_code == 200
    assert len(zones.json()) == 4


def test_device_create_uses_zone_lookup(client):
    response = client.post(
        "/devices/",
        json={
            "name": "Test PLC",
            "ip_address": "10.0.30.88",
            "zone": "Fallback Zone",
        },
    )

    assert response.status_code == 200
    created = response.json()
    assert created["zone"] == "Warehouse"
    assert created["status"] == "normal"


def test_monitor_ingest_creates_alert_and_quarantine_request(client):
    device = client.get("/devices/").json()[0]
    attack = _sample_features("1.mirai.ack.csv")

    response = client.post(
        "/monitor/ingest",
        json={"device_id": device["id"], "features": attack},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_anomaly"] is True
    assert payload["confidence"] >= 0.85
    assert payload["alert_id"]
    assert payload["quarantine_request_id"]

    alerts = client.get("/alerts/").json()
    requests = client.get("/quarantine/").json()
    updated_device = client.get(f"/devices/{device['id']}").json()

    assert any(alert["id"] == payload["alert_id"] for alert in alerts)
    assert any(item["id"] == payload["quarantine_request_id"] for item in requests)
    assert updated_device["status"] == "anomaly"


def test_benign_ingest_keeps_device_normal(client):
    device = client.get("/devices/").json()[0]
    benign = _sample_features("1.benign.csv")

    response = client.post(
        "/monitor/ingest",
        json={"device_id": device["id"], "features": benign},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_anomaly"] is False
    assert "alert_id" not in payload

    updated_device = client.get(f"/devices/{device['id']}").json()
    assert updated_device["status"] == "normal"


def test_quarantine_approval_and_release(client):
    device = client.get("/devices/").json()[0]
    attack = _sample_features("1.mirai.ack.csv")
    ingest = client.post(
        "/monitor/ingest",
        json={"device_id": device["id"], "features": attack},
    ).json()

    approve = client.post(
        f"/quarantine/{ingest['quarantine_request_id']}/approve",
        json={"approved_by": "pytest", "notes": "verified"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    assert client.get(f"/devices/{device['id']}").json()["status"] == "quarantined"

    release = client.post(f"/quarantine/{ingest['quarantine_request_id']}/release")
    assert release.status_code == 200
    assert release.json()["status"] == "released"
    assert client.get(f"/devices/{device['id']}").json()["status"] == "normal"


def test_report_generation_uses_fallback_without_api_key(client):
    demo = client.post("/demo/trigger-anomaly")
    assert demo.status_code == 200

    response = client.post(
        "/reports/generate",
        json={
            "alert_id": demo.json()["alert_id"],
            "additional_context": "pytest coverage",
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["title"]
    assert report["severity"] in {"critical", "high", "medium", "low"}
    assert report["full_report"]


def test_sqlite_state_persists_between_clients(client):
    created = client.post(
        "/devices/",
        json={
            "name": "Persistent Sensor",
            "ip_address": "10.0.20.99",
            "zone": "Admin Network",
        },
    ).json()

    from api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as second_client:
        fetched = second_client.get(f"/devices/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Persistent Sensor"

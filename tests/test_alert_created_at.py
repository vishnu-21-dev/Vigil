from __future__ import annotations

import sqlite3

import pytest

from api.store import _db_path


@pytest.fixture(autouse=True)
def _stub_inference(monkeypatch):
    monkeypatch.setattr(
        "api.routers.monitor.run_inference",
        lambda _features: {"label": 1, "confidence": 0.97, "is_anomaly": True},
    )


def test_created_at_orders_by_time_across_demo_and_ingest_alerts(client):
    devices = client.get("/devices/").json()
    ingest_device = devices[1]

    # Ingest first (older), then demo (newer): list order must follow time.
    older = client.post(
        "/monitor/ingest", json={"device_id": ingest_device["id"], "features": {}}
    ).json()["alert_id"]
    newer = client.post("/demo/trigger-anomaly").json()["alert_id"]

    assert [a["id"] for a in client.get("/alerts/").json()] == [older, newer]

    with sqlite3.connect(_db_path()) as connection:
        columns = dict(connection.execute("SELECT id, created_at FROM alerts"))
    assert "T" in columns[older] and "T" in columns[newer], columns

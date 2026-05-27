from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from api.config import settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _db_path() -> Path:
    path = Path(settings.db_path).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                acknowledged INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS quarantine_requests (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS zones (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            );
            """
        )


def reset_store() -> None:
    with _connect() as connection:
        for table in ("devices", "alerts", "quarantine_requests", "reports", "zones"):
            connection.execute(f"DELETE FROM {table}")


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(_json_ready(payload), sort_keys=True)


def _load(payload: str) -> dict[str, Any]:
    return json.loads(payload)


def _load_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [deepcopy(_load(row["payload"])) for row in rows]


def get_all_devices() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT payload FROM devices ORDER BY rowid").fetchall()
    return _load_rows(rows)


def get_device(device_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM devices WHERE id = ?",
            (device_id,),
        ).fetchone()
    return deepcopy(_load(row["payload"])) if row is not None else None


def add_device(device: dict[str, Any]) -> dict[str, Any]:
    stored_device = deepcopy(device)
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO devices (id, payload)
            VALUES (?, ?)
            """,
            (stored_device["id"], _dump(stored_device)),
        )
    return deepcopy(stored_device)


def update_device(device_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    device = get_device(device_id)
    if device is None:
        return None

    device.update(deepcopy(updates))
    return add_device(device)


def delete_device(device_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    return cursor.rowcount > 0


def get_all_alerts(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT payload FROM alerts"
    params: tuple[str, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY created_at"

    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return _load_rows(rows)


def _store_alert(alert: dict[str, Any]) -> dict[str, Any]:
    stored_alert = deepcopy(alert)
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO alerts
                (id, status, acknowledged, created_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                stored_alert["id"],
                stored_alert["status"],
                int(bool(stored_alert.get("acknowledged", False))),
                str(stored_alert["created_at"]),
                _dump(stored_alert),
            ),
        )
    return deepcopy(stored_alert)


def add_alert(alert: dict[str, Any]) -> dict[str, Any]:
    stored_alert = deepcopy(alert)
    stored_alert.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    stored_alert.setdefault("acknowledged", False)
    return _store_alert(stored_alert)


def get_active_unacknowledged_alerts() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT payload FROM alerts
            WHERE status = 'active' AND acknowledged = 0
            ORDER BY created_at
            """
        ).fetchall()
    return _load_rows(rows)


def acknowledge_alert(alert_id: str) -> None:
    alert = next((item for item in get_all_alerts() if item["id"] == alert_id), None)
    if alert is None:
        return

    alert["acknowledged"] = True
    _store_alert(alert)


def resolve_alert(alert_id: str) -> dict[str, Any] | None:
    alert = next((item for item in get_all_alerts() if item["id"] == alert_id), None)
    if alert is None:
        return None

    alert["acknowledged"] = True
    alert["status"] = "resolved"
    return _store_alert(alert)


def get_all_quarantine_requests(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT payload FROM quarantine_requests"
    params: tuple[str, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY rowid"

    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return _load_rows(rows)


def get_quarantine_request(request_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM quarantine_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
    return deepcopy(_load(row["payload"])) if row is not None else None


def add_quarantine_request(request: dict[str, Any]) -> dict[str, Any]:
    stored_request = deepcopy(request)
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO quarantine_requests (id, status, payload)
            VALUES (?, ?, ?)
            """,
            (stored_request["id"], stored_request["status"], _dump(stored_request)),
        )
    return deepcopy(stored_request)


def update_quarantine_request(
    request_id: str, updates: dict[str, Any]
) -> dict[str, Any] | None:
    request = get_quarantine_request(request_id)
    if request is None:
        return None

    request.update(deepcopy(updates))
    return add_quarantine_request(request)


def get_all_reports() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT payload FROM reports ORDER BY created_at").fetchall()
    return _load_rows(rows)


def get_report(report_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    return deepcopy(_load(row["payload"])) if row is not None else None


def add_report(report: dict[str, Any]) -> dict[str, Any]:
    stored_report = deepcopy(report)
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO reports (id, created_at, payload)
            VALUES (?, ?, ?)
            """,
            (
                stored_report["id"],
                str(stored_report["created_at"]),
                _dump(stored_report),
            ),
        )
    return deepcopy(stored_report)


def get_all_zones() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT payload FROM zones ORDER BY rowid").fetchall()
    return _load_rows(rows)


def get_zone(zone_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM zones WHERE id = ?",
            (zone_id,),
        ).fetchone()
    return deepcopy(_load(row["payload"])) if row is not None else None


def get_zone_by_name(name: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM zones WHERE name = ?",
            (name,),
        ).fetchone()
    return deepcopy(_load(row["payload"])) if row is not None else None


def add_zone(zone: dict[str, Any]) -> dict[str, Any]:
    stored_zone = deepcopy(zone)
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO zones (id, name, payload)
            VALUES (?, ?, ?)
            """,
            (stored_zone["id"], stored_zone["name"], _dump(stored_zone)),
        )
    return deepcopy(stored_zone)


def update_zone(zone_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    zone = get_zone(zone_id)
    if zone is None:
        return None

    zone.update(deepcopy(updates))
    return add_zone(zone)


def delete_zone(zone_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
    return cursor.rowcount > 0


def find_zone_for_ip(ip_address: str) -> dict[str, Any] | None:
    try:
        target_ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return None

    for zone in get_all_zones():
        try:
            start_ip = ipaddress.ip_address(zone["ip_range_start"])
            end_ip = ipaddress.ip_address(zone["ip_range_end"])
        except ValueError:
            continue

        if start_ip <= target_ip <= end_ip:
            return deepcopy(zone)

    return None


init_db()

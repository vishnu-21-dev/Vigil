from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from api import store
from api.config import settings
from api.store import (
    acknowledge_alert,
    add_quarantine_request,
    get_active_unacknowledged_alerts,
    get_alert,
    get_all_quarantine_requests,
    get_all_reports,
    get_device,
    transaction,
    update_alert,
    update_device,
    update_quarantine_request,
    add_report,
)
from api.groq_client import generate_incident_report


FAILSAFE_TIMEOUT = settings.failsafe_timeout
# Auto-quarantine only at >= 0.95. On held-out devices, false alarms on benign traffic
# cluster at 0.85-0.90 (ml/audit/RESULTS.md section 4); lower-confidence alerts still
# reach a human, they just are not contained automatically.
FAILSAFE_THRESHOLD = 0.95
logger = logging.getLogger("uvicorn.error")


def _parse_created_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def failsafe_deadline(alert: dict[str, Any]) -> datetime:
    """When the failsafe may act: 120s after creation, or later if a restart granted grace."""
    deadline = _parse_created_at(alert["created_at"]) + timedelta(seconds=FAILSAFE_TIMEOUT)
    grace = alert.get("failsafe_grace_until")
    return max(deadline, _parse_created_at(grace)) if grace else deadline


def grant_restart_grace() -> int:
    """Give alerts that went overdue while the server was down one fresh window.

    Operators could not see or answer them during the downtime, so containing all of
    them on the first tick after a restart would be a burst no human could review.
    Each alert gets this at most once, so a crash loop cannot postpone it forever.
    """
    now = datetime.now(timezone.utc)
    until = now + timedelta(seconds=FAILSAFE_TIMEOUT)
    granted = 0
    with transaction():
        for alert in get_active_unacknowledged_alerts():
            try:
                overdue = failsafe_deadline(alert) <= now
            except (KeyError, TypeError, ValueError):
                continue
            if overdue and not alert.get("failsafe_grace_until"):
                update_alert(alert["id"], {"failsafe_grace_until": until})
                granted += 1
    if granted:
        logger.warning(
            "Restart: %d overdue alert(s) get a fresh %ss before the AI failsafe acts",
            granted,
            FAILSAFE_TIMEOUT,
        )
    return granted


def _contain(alert_id: str, elapsed: float, confidence: float) -> tuple[dict, dict] | None:
    """Acknowledge and contain in one transaction; None if a human got there first."""
    with transaction():
        # Re-read inside the lock: the tick's snapshot may be stale (e.g. a human
        # approved or dismissed in the meantime), and nobody can change it now.
        current_alert = get_alert(alert_id)
        if (
            current_alert is None
            or current_alert.get("acknowledged")
            or current_alert.get("status") != "active"
        ):
            return None
        device = get_device(current_alert["device_id"])
        if not device or device["status"] != "anomaly":
            return None

        now = datetime.now(timezone.utc)
        containment = {
            "status": "ai_contained",
            "approved_by": "AI Failsafe",
            "approved_at": now,
            "reason": (
                f"No operator response after {int(elapsed)}s. "
                f"Model confidence {confidence:.0%} exceeded threshold of "
                f"{FAILSAFE_THRESHOLD:.0%}."
            ),
            "requires_human_approval": False,
            "triggered_by": "AI_FAILSAFE",
            "auto_contained_at": now,
            "alert_id": alert_id,
        }

        pending = next(
            (
                item
                for item in get_all_quarantine_requests(status="pending")
                if item["device_id"] == device["id"]
            ),
            None,
        )
        if pending is not None:
            update_quarantine_request(pending["id"], containment)
        else:
            add_quarantine_request(
                {
                    "id": str(uuid.uuid4()),
                    "device_id": device["id"],
                    "device_name": device["name"],
                    "zone": device["zone"],
                    "confidence": confidence,
                    "flagged_at": _parse_created_at(current_alert["created_at"]),
                    **containment,
                }
            )
        update_device(device["id"], {"status": "quarantined"})
        # Same as a human decision: every open alert on this device is now handled.
        for other in store.get_active_unacknowledged_alerts():
            if other["device_id"] == device["id"]:
                acknowledge_alert(other["id"])
    return current_alert, device


def _write_containment_report(alert: dict[str, Any], device: dict[str, Any]) -> None:
    alert_for_report = dict(alert)
    alert_for_report["additional_context"] = "Automatically generated during AI Failsafe containment."

    generated = generate_incident_report(alert_for_report, device)
    add_report(
        {
            "id": str(uuid.uuid4()),
            "title": generated["title"],
            "device_id": device["id"],
            "device_name": device["name"],
            "zone": device["zone"],
            "severity": generated["severity"],
            "summary": generated["summary"],
            "full_report": generated["full_report"],
            "source": generated["source"],
            "affected_devices": [device["name"]],
            "created_at": datetime.now(timezone.utc),
            "alert_id": alert["id"],
        }
    )


def auto_quarantine(alert: dict[str, Any], elapsed: float, confidence: float) -> None:
    contained = _contain(alert["id"], elapsed, confidence)
    if contained is None:
        return
    current_alert, device = contained

    # The slow report runs after the commit so it never holds the write lock. If the
    # process dies before it is stored, backfill_missing_reports writes it at startup.
    try:
        _write_containment_report(current_alert, device)
    except Exception as e:
        logger.error(f"Failed to generate incident report during AI containment: {e}")

    logger.info(
        "AI failsafe contained device_id=%s alert_id=%s elapsed=%ss confidence=%.2f",
        device["id"],
        alert["id"],
        int(elapsed),
        confidence,
    )


def backfill_missing_reports() -> int:
    """Write the report for any AI containment whose report was lost (e.g. a crash)."""
    reported = {report.get("alert_id") for report in get_all_reports()}
    written = 0
    for request in get_all_quarantine_requests(status="ai_contained"):
        alert_id = request.get("alert_id")
        if not alert_id or alert_id in reported:
            continue
        alert = get_alert(alert_id)
        device = get_device(request["device_id"])
        if alert is None or device is None:
            continue
        try:
            _write_containment_report(alert, device)
            written += 1
        except Exception:
            logger.exception("Could not backfill report for alert_id=%s", alert_id)
    if written:
        logger.warning("Backfilled %d missing AI containment report(s)", written)
    return written


FAILSAFE_TICK_SECONDS = 2


async def failsafe_loop() -> None:
    while True:
        await asyncio.sleep(FAILSAFE_TICK_SECONDS)
        try:
            now = datetime.now(timezone.utc)
            alerts = get_active_unacknowledged_alerts()
        except Exception:
            logger.exception("AI failsafe tick could not fetch alerts")
            continue

        for alert in alerts:
            try:
                created = _parse_created_at(alert["created_at"])
                elapsed = (now - created).total_seconds()
                confidence = float(alert.get("confidence", 0))

                if now >= failsafe_deadline(alert) and confidence >= FAILSAFE_THRESHOLD:
                    await asyncio.to_thread(auto_quarantine, alert, elapsed, confidence)
            except Exception:
                logger.exception(
                    "AI failsafe failed processing alert_id=%s", alert.get("id")
                )

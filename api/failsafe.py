from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from api.store import (
    acknowledge_alert,
    add_quarantine_request,
    get_active_unacknowledged_alerts,
    get_device,
    update_device,
    add_report,
)
from api.groq_client import generate_incident_report


FAILSAFE_TIMEOUT = 120
FAILSAFE_THRESHOLD = 0.85
logger = logging.getLogger("uvicorn.error")


def _parse_created_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def auto_quarantine(alert: dict[str, Any], elapsed: float, confidence: float) -> None:
    device = get_device(alert["device_id"])
    if not device:
        return

    now = datetime.now(timezone.utc)

    request = {
        "id": str(uuid.uuid4()),
        "device_id": device["id"],
        "device_name": device["name"],
        "zone": device["zone"],
        "confidence": confidence,
        "flagged_at": _parse_created_at(alert["created_at"]),
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
    }

    add_quarantine_request(request)
    update_device(device["id"], {"status": "quarantined"})
    
    try:
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
                "affected_devices": [device["name"]],
                "created_at": now,
                "alert_id": alert["id"],
            }
        )
    except Exception as e:
        logger.error(f"Failed to generate incident report during AI containment: {e}")

    logger.info(
        "AI failsafe contained device_id=%s alert_id=%s elapsed=%ss confidence=%.2f",
        device["id"],
        alert["id"],
        int(elapsed),
        confidence,
    )


async def failsafe_loop() -> None:
    while True:
        await asyncio.sleep(10)
        now = datetime.now(timezone.utc)
        for alert in get_active_unacknowledged_alerts():
            created = _parse_created_at(alert["created_at"])
            elapsed = (now - created).total_seconds()
            confidence = float(alert.get("confidence", 0))

            if elapsed >= FAILSAFE_TIMEOUT and confidence >= FAILSAFE_THRESHOLD:
                acknowledge_alert(alert["id"])
                auto_quarantine(alert, elapsed, confidence)

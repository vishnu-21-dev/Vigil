from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.failsafe import FAILSAFE_TIMEOUT
from api.schemas import AlertResponse
from api.store import get_all_alerts, get_device, resolve_alert, update_device


VALID_ALERT_STATUSES = {"active", "resolved"}

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=list[AlertResponse])
def list_alerts(status: str | None = Query(default=None)) -> list[AlertResponse]:
    if status is not None and status not in VALID_ALERT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid alert status filter.")

    return [AlertResponse(**alert, failsafe_timeout=FAILSAFE_TIMEOUT) for alert in get_all_alerts(status=status)]


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: str) -> AlertResponse:
    for alert in get_all_alerts():
        if alert["id"] == alert_id:
            return AlertResponse(**alert, failsafe_timeout=FAILSAFE_TIMEOUT)
    raise HTTPException(status_code=404, detail="Alert not found.")


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_existing_alert(alert_id: str) -> AlertResponse:
    alert = resolve_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    device = get_device(alert["device_id"])
    if device is not None:
        update_device(
            device["id"],
            {
                "status": "normal",
                "anomaly_score": 0.0,
            },
        )

    return AlertResponse(**alert, failsafe_timeout=FAILSAFE_TIMEOUT)

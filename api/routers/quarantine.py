from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    QuarantineApproval,
    QuarantineRequestCreate,
    QuarantineResponse,
)
from api.store import (
    acknowledge_alert,
    add_quarantine_request,
    get_active_unacknowledged_alerts,
    get_all_quarantine_requests,
    get_device,
    get_quarantine_request,
    update_device,
    update_quarantine_request,
)


VALID_QUARANTINE_STATUSES = {
    "pending",
    "approved",
    "dismissed",
    "released",
    "ai_contained",
}

router = APIRouter(prefix="/quarantine", tags=["quarantine"])


@router.post("/request", response_model=QuarantineResponse)
def create_quarantine_request(
    request: QuarantineRequestCreate,
) -> QuarantineResponse:
    device = get_device(request.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    if device["status"] != "anomaly":
        raise HTTPException(
            status_code=400,
            detail="Device must be in anomaly status before quarantine review.",
        )

    created = add_quarantine_request(
        {
            "id": __import__("uuid").uuid4().hex,
            "device_id": device["id"],
            "device_name": device["name"],
            "zone": device["zone"],
            "confidence": float(device.get("anomaly_score", 0.0)),
            "flagged_at": datetime.now(timezone.utc),
            "status": "pending",
            "approved_by": None,
            "approved_at": None,
            "reason": request.reason,
            "requires_human_approval": True,
        }
    )
    for alert in get_active_unacknowledged_alerts():
        if alert["device_id"] == device["id"]:
            acknowledge_alert(alert["id"])
    return QuarantineResponse(**created)


@router.get("/", response_model=list[QuarantineResponse])
def list_quarantine_requests(
    status: str | None = Query(default=None),
) -> list[QuarantineResponse]:
    if status is not None and status not in VALID_QUARANTINE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid quarantine status filter.")
    return [
        QuarantineResponse(**request)
        for request in get_all_quarantine_requests(status=status)
    ]


@router.get("/{request_id}", response_model=QuarantineResponse)
def get_quarantine_request_by_id(request_id: str) -> QuarantineResponse:
    request = get_quarantine_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Quarantine request not found.")
    return QuarantineResponse(**request)


@router.post("/{request_id}/approve", response_model=QuarantineResponse)
def approve_quarantine_request(
    request_id: str, approval: QuarantineApproval
) -> QuarantineResponse:
    request = get_quarantine_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Quarantine request not found.")

    now = datetime.now(timezone.utc)
    updated_request = update_quarantine_request(
        request_id,
        {
            "status": "approved",
            "approved_by": approval.approved_by,
            "approved_at": now,
            "reason": request["reason"]
            if approval.notes is None
            else f"{request['reason']} | Notes: {approval.notes}",
            "requires_human_approval": True,
        },
    )
    update_device(request["device_id"], {"status": "quarantined"})
    return QuarantineResponse(**updated_request)


@router.post("/{request_id}/dismiss", response_model=QuarantineResponse)
def dismiss_quarantine_request(request_id: str) -> QuarantineResponse:
    request = get_quarantine_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Quarantine request not found.")

    updated_request = update_quarantine_request(
        request_id,
        {
            "status": "dismissed",
            "requires_human_approval": True,
        },
    )
    update_device(request["device_id"], {"status": "normal", "anomaly_score": 0.0})
    return QuarantineResponse(**updated_request)


@router.post("/{request_id}/release", response_model=QuarantineResponse)
def release_quarantined_device(request_id: str) -> QuarantineResponse:
    request = get_quarantine_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Quarantine request not found.")
    if request["status"] not in {"approved", "ai_contained"}:
        raise HTTPException(
            status_code=400,
            detail="Only approved or AI-contained quarantine requests can be released.",
        )

    updated_request = update_quarantine_request(
        request_id,
        {
            "status": "released",
            "requires_human_approval": True,
        },
    )
    update_device(request["device_id"], {"status": "normal", "anomaly_score": 0.0})
    return QuarantineResponse(**updated_request)

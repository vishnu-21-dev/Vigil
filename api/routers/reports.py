from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from api.groq_client import generate_incident_report
from api.schemas import ReportGenerateRequest, ReportResponse
from api.store import add_report, get_all_alerts, get_all_reports, get_device, get_report


router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate", response_model=ReportResponse)
def generate_report(request: ReportGenerateRequest) -> ReportResponse:
    alert = next((item for item in get_all_alerts() if item["id"] == request.alert_id), None)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    device = get_device(alert["device_id"])
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")

    alert_for_report = dict(alert)
    if request.additional_context:
        alert_for_report["additional_context"] = request.additional_context

    generated = generate_incident_report(alert_for_report, device)
    report = add_report(
        {
            "id": str(uuid4()),
            "title": generated["title"],
            "device_id": device["id"],
            "device_name": device["name"],
            "zone": device["zone"],
            "severity": generated["severity"],
            "summary": generated["summary"],
            "full_report": generated["full_report"],
            "affected_devices": [device["name"]],
            "created_at": datetime.now(timezone.utc),
            "alert_id": alert["id"],
        }
    )
    return ReportResponse(**report)


@router.get("/", response_model=list[ReportResponse])
def list_reports() -> list[ReportResponse]:
    reports = sorted(
        get_all_reports(),
        key=lambda report: report["created_at"],
        reverse=True,
    )
    return [ReportResponse(**report) for report in reports]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report_by_id(report_id: str) -> ReportResponse:
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return ReportResponse(**report)

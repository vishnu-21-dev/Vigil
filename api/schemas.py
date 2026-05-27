from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DeviceBase(BaseModel):
    id: str
    name: str
    ip_address: str
    zone: str


class DeviceCreate(BaseModel):
    name: str
    ip_address: str
    zone: str


class DeviceResponse(BaseModel):
    id: str
    name: str
    ip_address: str
    zone: str
    status: str
    last_seen: datetime
    anomaly_score: float


class ZoneCreate(BaseModel):
    name: str
    description: str | None = None
    subnet: str
    ip_range_start: str
    ip_range_end: str


class ZoneUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    subnet: str | None = None
    ip_range_start: str | None = None
    ip_range_end: str | None = None


class ZoneResponse(BaseModel):
    id: str
    name: str
    description: str | None
    subnet: str
    ip_range_start: str
    ip_range_end: str
    device_count: int
    created_at: datetime


class BehaviorReading(BaseModel):
    device_id: str
    features: dict[str, float]


class AlertResponse(BaseModel):
    id: str
    device_id: str
    device_name: str
    alert_type: str
    confidence: float
    timestamp: datetime
    zone: str
    status: Literal["active", "resolved"]
    created_at: datetime
    acknowledged: bool = False
    failsafe_timeout: int = 120


class QuarantineRequestCreate(BaseModel):
    device_id: str
    reason: str


class QuarantineApproval(BaseModel):
    approved_by: str
    notes: str | None = None


class QuarantineResponse(BaseModel):
    id: str
    device_id: str
    device_name: str
    zone: str
    confidence: float
    flagged_at: datetime
    status: Literal["pending", "approved", "dismissed", "released", "ai_contained"]
    approved_by: str | None
    approved_at: datetime | None
    reason: str
    requires_human_approval: bool = True
    triggered_by: str | None = None
    auto_contained_at: datetime | None = None


class ReportGenerateRequest(BaseModel):
    alert_id: str
    additional_context: str | None = None


class ReportResponse(BaseModel):
    id: str
    title: str
    device_id: str
    device_name: str
    zone: str
    severity: str
    summary: str
    full_report: str
    affected_devices: list[str]
    created_at: datetime
    alert_id: str


class AnomalyResult(BaseModel):
    device_id: str
    is_anomaly: bool
    confidence: float
    timestamp: datetime

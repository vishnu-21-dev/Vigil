from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from api.ml_bridge import run_inference
from api.schemas import BehaviorReading
from api.store import (
    add_alert,
    add_quarantine_request,
    get_all_devices,
    get_device,
    update_device,
)


router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.post("/ingest")
def ingest_behavior(reading: BehaviorReading) -> dict[str, object]:
    device = get_device(reading.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")

    inference = run_inference(reading.features)
    if "error" in inference:
        raise HTTPException(status_code=503, detail=inference["error"])

    confidence = float(inference["confidence"])
    now = datetime.now(timezone.utc)

    if inference["is_anomaly"]:
        updated_device = update_device(
            reading.device_id,
            {
                "status": "anomaly",
                "last_seen": now,
                "anomaly_score": confidence,
            },
        )
        if updated_device is None:
            raise HTTPException(status_code=404, detail="Device not found.")

        alert = add_alert(
            {
                "id": str(uuid4()),
                "device_id": device["id"],
                "device_name": device["name"],
                "alert_type": "Anomaly Detected",
                "confidence": confidence,
                "timestamp": now,
                "zone": device["zone"],
                "status": "active",
            }
        )
        quarantine_request = add_quarantine_request(
            {
                "id": str(uuid4()),
                "device_id": device["id"],
                "device_name": device["name"],
                "zone": device["zone"],
                "confidence": confidence,
                "flagged_at": now,
                "status": "pending",
                "approved_by": None,
                "approved_at": None,
                "reason": "Automatically flagged from anomaly detection.",
            }
        )

        return {
            "device_id": reading.device_id,
            "is_anomaly": True,
            "confidence": confidence,
            "alert_id": alert["id"],
            "quarantine_request_id": quarantine_request["id"],
        }

    updated_device = update_device(
        reading.device_id,
        {
            "last_seen": now,
            "anomaly_score": confidence,
            "status": "normal",
        },
    )
    if updated_device is None:
        raise HTTPException(status_code=404, detail="Device not found.")

    return {
        "device_id": reading.device_id,
        "is_anomaly": False,
        "confidence": confidence,
    }


@router.get("/")
def monitor_root() -> dict[str, str]:
    return {"message": "monitor router live"}


@router.post("/demo/trigger-anomaly")
def trigger_demo_anomaly() -> dict[str, str]:
    devices = get_all_devices()
    device = next(
        (item for item in devices if item["status"] != "quarantined"),
        devices[0] if devices else None,
    )
    if device is None:
        raise HTTPException(status_code=404, detail="No demo device available.")

    now = datetime.now(timezone.utc)
    confidence = 0.97
    update_device(
        device["id"],
        {
            "status": "anomaly",
            "last_seen": now,
            "anomaly_score": confidence,
        },
    )
    alert = add_alert(
        {
            "id": str(uuid4()),
            "device_id": device["id"],
            "device_name": device["name"],
            "alert_type": "C&C Communication",
            "confidence": confidence,
            "timestamp": now,
            "zone": device["zone"],
            "status": "active",
            "created_at": now,
            "acknowledged": False,
        }
    )
    return {"alert_id": alert["id"], "message": "Demo anomaly injected"}


# if __name__ == "__main__":
#     example_payload = {
#         "device_id": "example-device-id",
#         "features": {
#             "MI_dir_L5_weight": 1.0,
#             "MI_dir_L5_mean": 60.0,
#             "MI_dir_L5_variance": 0.0,
#             "MI_dir_L3_weight": 1.0,
#             "MI_dir_L3_mean": 60.0,
#             "MI_dir_L3_variance": 0.0,
#             "MI_dir_L1_weight": 1.0,
#             "MI_dir_L1_mean": 60.0,
#             "MI_dir_L1_variance": 0.0,
#             "MI_dir_L0.1_weight": 1.0,
#             "H_L5_weight": 1.0,
#             "H_L5_mean": 60.0,
#             "HH_L5_weight": 1.0,
#             "HH_L5_mean": 60.0,
#             "HpHp_L0.01_covariance": 0.0,
#             "HpHp_L0.01_pcc": 0.0,
#         },
#     }
#     print(example_payload)

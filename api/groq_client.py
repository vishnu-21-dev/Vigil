from __future__ import annotations

import json
from typing import Any

from api.config import settings


def _severity_from_confidence(confidence: float) -> str:
    if confidence > 0.9:
        return "critical"
    if confidence > 0.75:
        return "high"
    if confidence > 0.5:
        return "medium"
    return "low"


def _fallback_report(alert: dict[str, Any], device: dict[str, Any]) -> dict[str, str]:
    confidence = float(alert.get("confidence", 0.0))
    severity = _severity_from_confidence(confidence)
    title = f"Incident Report: {device['name']} behavioral anomaly"
    summary = (
        f"An anomalous behavioral pattern was detected on {device['name']} "
        f"in the {device['zone']} zone with confidence {confidence:.2f}."
    )
    full_report = "\n".join(
        [
            f"Title: {title}",
            f"Severity: {severity}",
            "",
            "Executive Summary:",
            summary,
            "The device should be reviewed by the security operations team.",
            "",
            "Technical Details:",
            f"- Alert type: {alert.get('alert_type', 'Anomaly Detected')}",
            f"- Device ID: {device['id']}",
            f"- Device name: {device['name']}",
            f"- Zone: {device['zone']}",
            f"- Confidence score: {confidence:.2f}",
            "",
            "Recommended Actions:",
            "- Validate the traffic pattern against recent operational changes.",
            "- Review device communication peers and recent access attempts.",
            "- Confirm whether quarantine approval is required.",
            "- Capture packet and host telemetry for deeper investigation.",
        ]
    )
    return {
        "title": title,
        "severity": severity,
        "summary": summary,
        "full_report": full_report,
    }


def generate_incident_report(alert: dict[str, Any], device: dict[str, Any]) -> dict[str, str]:
    confidence = float(alert.get("confidence", 0.0))
    severity = _severity_from_confidence(confidence)
    fallback = _fallback_report(alert, device)
    api_key = settings.groq_api_key.strip()

    if not api_key:
        return fallback

    try:
        from groq import APIError, RateLimitError, Groq

        client = Groq(api_key=api_key)
        prompt = f"""
You are generating a security incident report for an industrial IoT defense system.
Return valid JSON only with keys: title, severity, summary, full_report.

Incident data:
- Device name: {device["name"]}
- Device ID: {device["id"]}
- IP address: {device["ip_address"]}
- Zone: {device["zone"]}
- Alert type: {alert.get("alert_type", "Anomaly Detected")}
- Confidence score: {confidence:.4f}
- Severity must be: {severity}
- Additional context: {alert.get("additional_context", "")}

Requirements:
- Title: concise and executive-friendly
- Severity: one of critical/high/medium/low
- Summary: 2-3 non-technical sentences
- Full report: include technical details and 3-5 recommended action bullets
"""
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a careful cybersecurity incident reporting assistant.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = completion.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return {
            "title": str(parsed.get("title") or fallback["title"]),
            "severity": str(parsed.get("severity") or severity).lower(),
            "summary": str(parsed.get("summary") or fallback["summary"]),
            "full_report": str(parsed.get("full_report") or fallback["full_report"]),
        }
    except Exception as exc:
        error_name = exc.__class__.__name__
        if error_name in {"RateLimitError", "APIError"}:
            return fallback
        return fallback

"""One-command check that incident reports come from the LLM, not the fallback template.

Run from the repo root:  python scripts/check_report_source.py
Reads GROQ_API_KEY / GROQ_MODEL from .env (the key is never printed). Sends one
made-up incident to Groq. Prints "STORED SOURCE: LLM" or "STORED SOURCE: FALLBACK",
plus the logged warning explaining a fallback.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.groq_client import generate_incident_report  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

ALERT = {"alert_type": "C&C Communication", "confidence": 0.97, "zone": "Production Floor"}
DEVICE = {"id": "check-device-1", "name": "Check Device", "ip_address": "10.0.0.1", "zone": "Production Floor"}

source = generate_incident_report(ALERT, DEVICE)["source"]
print(f"STORED SOURCE: {source.upper()}")
sys.exit(0 if source == "llm" else 1)

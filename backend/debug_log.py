"""Formatted AI diagnostics persisted separately from the server console."""

import logging
import time
from pathlib import Path


# View: implementation-architecture.svg#O5
# Persist diagnostics separately from HTTP console logs. Response text can include
# sensitive medical content; the log belongs with private library data.
logger = logging.getLogger("family_medical_records.ai")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    path = Path(__file__).resolve().parents[1] / "data" / "backend.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8", delay=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)

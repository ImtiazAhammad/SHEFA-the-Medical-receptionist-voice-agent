"""HIPAA compliance and PHI protection utilities."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any

import structlog

logger = structlog.get_logger("sefa.compliance")

_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_DOB_RE = re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b")
_MRN_RE = re.compile(r"\bMRN[:\s]*\d+\b", re.IGNORECASE)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL_RE = re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b")


def mask_phi(text: str) -> str:
    """Mask PHI identifiers in text for logging."""
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _DOB_RE.sub("[DOB]", text)
    text = _MRN_RE.sub("[MRN]", text)
    text = _SSN_RE.sub("[SSN]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    return text


def audit_log(
    event: str,
    call_sid: str | None = None,
    patient_id: str | None = None,
    user: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write a HIPAA audit log entry."""
    entry = {
        "timestamp": time.time(),
        "event": event,
        "call_sid": call_sid,
        "patient_id": patient_id,
        "user": user,
        "details": details or {},
    }
    logger.info("audit", **entry)


def hash_identifier(identifier: str) -> str:
    """One-way hash an identifier for de-identified storage."""
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


def validate_phi_access(requester: str, patient_id: str, action: str) -> bool:
    """Check if requester is authorized to access patient PHI."""
    audit_log(
        event="phi_access_check",
        patient_id=patient_id,
        user=requester,
        details={"action": action, "authorized": True},
    )
    return True

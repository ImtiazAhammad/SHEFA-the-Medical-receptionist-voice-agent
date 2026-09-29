"""HIPAA compliance and PHI protection utilities."""

from __future__ import annotations

import hashlib
import re
import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sefa.auth import AuthStore

logger = structlog.get_logger("sefa.compliance")

_E164_RE = re.compile(r"\+(\d{8,15})")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_DOB_RE = re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b")
_MRN_RE = re.compile(r"\bMRN[:\s]*\d+\b", re.IGNORECASE)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL_RE = re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b")


def _keep_last_four(match: re.Match[str]) -> str:
    """`+8801712345678` → `[PHONE]...5678`: reveal only the tail.

    The US 10-digit pattern would otherwise match a slice of the BD caller ID
    and leave a live residual (`678`) in the log — worse than an unlabelled
    number, because it looks masked.
    """
    return f"[PHONE]...{match.group(1)[-4:]}"


def mask_phi(text: str) -> str:
    """Mask PHI identifiers in text for logging."""
    text = _E164_RE.sub(_keep_last_four, text)
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
    logger.info(entry["event"], **{k: v for k, v in entry.items() if k != "event"})


def hash_identifier(identifier: str) -> str:
    """One-way hash an identifier for de-identified storage."""
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


# A PHI "action" is expressed as the permission that authorizes it, so the
# gate stays in lock-step with the route permission map rather than inventing a
# parallel hierarchy that drifts.
PHI_ACTION_PERMISSIONS: dict[str, str] = {
    "read": "sessions:read",
    "call": "calls:place",
}


def validate_phi_access(
    requester: str, patient_id: str, action: str, store: AuthStore
) -> bool:
    """Decide whether `requester` may perform `action` on `patient_id`'s PHI.

    The previous stub logged `authorized: True` for everyone: a decision that
    is always yes is not a decision, and an audit trail that never says no reads
    as evidence. This resolves the requester *by name*, which is a claimed
    identity — it authorizes a caller that already passed real authentication,
    it does not authenticate one. Every verdict, yes or no, is audited with its
    true value.
    """
    permission = PHI_ACTION_PERMISSIONS.get(action)
    principal = store.principal_named(requester) if permission is not None else None
    authorized = principal is not None and store.authorizes(principal, permission)

    details: dict[str, Any] = {"action": action, "authorized": authorized}
    if permission is None:
        details["reason"] = "unknown_action"
    audit_log(
        event="phi_access_granted" if authorized else "phi_access_denied",
        patient_id=patient_id,
        user=requester,
        details=details,
    )
    return authorized

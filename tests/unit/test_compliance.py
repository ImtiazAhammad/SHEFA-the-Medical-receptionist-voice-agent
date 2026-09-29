"""Tests for compliance utilities."""

from sefa.auth import AuthStore, hash_token
from sefa.utils.compliance import (
    audit_log,
    hash_identifier,
    mask_phi,
    validate_phi_access,
)

_TOKEN = "test-clinician-token-abcdefghijkl"


def test_mask_phone():
    masked = mask_phi("Call me at 555-123-4567")
    assert "555" not in masked
    assert "[PHONE]" in masked


def test_mask_bd_e164_phone_keeps_only_the_last_four():
    """D-ENG8: the US 10-digit regex misses — worse, half-eats — a BD caller ID.

    `+8801712345678` must be masked wholesale. The old US regex matched ten of
    its thirteen digits (`8801712345`) and left a bare `678` standing right
    after the marker, so a "masked" log still leaked the tail of a live number.
    """
    masked = mask_phi("Reach me at +8801712345678 please")
    assert "+8801712345678" not in masked
    assert "8801712345" not in masked
    assert "]678" not in masked
    assert "[PHONE]...5678" in masked


def test_mask_e164_phone_is_exactly_keep_last_four():
    assert mask_phi("+8801712345678") == "[PHONE]...5678"
    assert mask_phi("+15551234567") == "[PHONE]...4567"


def test_mask_local_us_phone_keeps_masking_as_before():
    assert "[PHONE]" in mask_phi("555-123-4567")


def test_mask_e164_does_not_eat_adjacent_short_digits():
    masked = mask_phi("Dial +8801500111222 then press 1")
    assert "8801500111" not in masked
    assert "+8801500111222" not in masked


def test_mask_dob():
    masked = mask_phi("DOB: 1990-05-15")
    assert "1990" not in masked
    assert "[DOB]" in masked


def test_mask_email():
    masked = mask_phi("Email: john@example.com")
    assert "john@example.com" not in masked
    assert "[EMAIL]" in masked


def test_mask_ssn():
    masked = mask_phi("SSN: 123-45-6789")
    assert "123-45-6789" not in masked
    assert "[SSN]" in masked


def test_hash_identifier():
    h = hash_identifier("PAT-001")
    assert len(h) == 16
    assert hash_identifier("PAT-001") == h
    assert hash_identifier("PAT-002") != h


def test_audit_log_does_not_duplicate_the_event_field():
    """The event is passed once; the old code raised a TypeError on itself."""
    audit_log("audit_test_event", patient_id="PAT-1", user="clinician")


def test_validate_phi_access_unknown_action_denies_with_true_verdict():
    store = AuthStore([("c", "clinician", hash_token(_TOKEN))], {"clinician": ["sessions:read"]})
    assert validate_phi_access("c", "PAT-1", "delete", store) is False

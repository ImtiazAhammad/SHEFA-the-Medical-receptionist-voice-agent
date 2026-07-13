"""Tests for compliance utilities."""

from sefa.utils.compliance import hash_identifier, mask_phi


def test_mask_phone():
    masked = mask_phi("Call me at 555-123-4567")
    assert "555" not in masked
    assert "[PHONE]" in masked


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

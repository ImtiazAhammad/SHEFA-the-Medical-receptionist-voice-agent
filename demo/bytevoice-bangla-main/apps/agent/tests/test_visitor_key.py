import json

from agent.security.visitor_key import open_visitor_key, seal_visitor_key, visitor_key_from_metadata

SECRET = "shared-internal-token"
VISITOR_KEY = "visitor-test-key-not-real-0123456789abcdef"


def test_round_trip() -> None:
    sealed = seal_visitor_key(VISITOR_KEY, SECRET, b"\x01" * 12)
    assert VISITOR_KEY not in sealed
    assert open_visitor_key(sealed, SECRET) == VISITOR_KEY


def test_wrong_secret_or_tampering_is_rejected() -> None:
    sealed = seal_visitor_key(VISITOR_KEY, SECRET, b"\x02" * 12)
    assert open_visitor_key(sealed, "another-secret") is None
    tampered = sealed[:-2] + ("A" if sealed[-2] != "A" else "B") + sealed[-1]
    assert open_visitor_key(tampered, SECRET) is None


def test_metadata_parsing() -> None:
    sealed = seal_visitor_key(VISITOR_KEY, SECRET, b"\x03" * 12)
    assert (
        visitor_key_from_metadata(json.dumps({"language": "bn", "sealed_api_key": sealed}), SECRET)
        == VISITOR_KEY
    )
    assert visitor_key_from_metadata(json.dumps({"language": "bn"}), SECRET) is None
    assert visitor_key_from_metadata("not json", SECRET) is None
    assert visitor_key_from_metadata(json.dumps({"sealed_api_key": sealed}), "") is None

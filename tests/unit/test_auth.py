"""Auth primitives: token hashing, verification, and role/permission resolution.

The service held transcripts, patient names, and an outbound-call trigger with no
credential at all, so anyone who reached the port could read every patient
conversation and place calls billed to the clinic.

Token storage is PBKDF2-HMAC-SHA256 with a per-principal salt so a leaked config
yields no usable token. The KDF is slow by design, and authn sits on the request
path, so each *verified* token is cached under `sha256(token)` — never the
plaintext. Only successes are cached, bounding the cache at the number of
configured principals, so a wrong guess still pays full KDF cost every attempt.
"""

from __future__ import annotations

import pytest

from sefa.auth import (
    DEFAULT_ITERATIONS,
    KDF_ALGORITHM,
    MIN_TOKEN_LENGTH,
    AuthStore,
    Principal,
    TokenError,
    generate_token,
    hash_token,
    verify_token,
)

# Iterations are 600k in production. Tests use a low count so the suite stays
# fast; every code path under test is identical.
FAST = {"iterations": 1_000}

ROLE_PERMISSIONS = {
    "viewer": ["sessions:read"],
    "clinician": ["sessions:read", "calls:place", "chat:use"],
    "admin": ["sessions:read", "calls:place", "chat:use", "config:read"],
}


def _store(**tokens: str) -> AuthStore:
    """Build a store from `role=token` keyword pairs; the role is the kwarg name."""
    principals = [
        (role, role, hash_token(value, **FAST)) for role, value in tokens.items()
    ]
    roles = {
        role: ROLE_PERMISSIONS[role] for role in tokens if role in ROLE_PERMISSIONS
    }
    return AuthStore(principals, roles)


class TestTokenGeneration:
    def test_generated_tokens_are_long_enough_to_be_keys(self):
        token = generate_token()

        assert len(token) >= MIN_TOKEN_LENGTH

    def test_generated_tokens_differ(self):
        assert generate_token() != generate_token()


class TestHashToken:
    def test_round_trips_through_verification(self):
        token = generate_token()

        assert verify_token(token, hash_token(token, **FAST)) is True

    def test_wrong_token_does_not_verify(self):
        record = hash_token(generate_token(), **FAST)

        assert verify_token("not-the-token", record) is False

    def test_the_same_token_hashes_differently_each_time(self):
        """Distinct salts, so identical tokens are not visibly identical.

        Without this, two operators who happened to configure the same token
        would show the same hash, and a rainbow table built from one config
        would crack the other.
        """
        token = generate_token()

        assert hash_token(token, **FAST) != hash_token(token, **FAST)

    def test_records_name_the_algorithm_and_iterations(self):
        record = hash_token(generate_token(), **FAST)
        algorithm, iterations, _salt, _digest = record.split("$")

        assert algorithm == KDF_ALGORITHM
        assert int(iterations) == FAST["iterations"]

    def test_the_default_is_a_slow_iteration_count(self):
        assert DEFAULT_ITERATIONS >= 200_000

    def test_a_record_never_contains_the_token(self):
        token = generate_token()

        assert token not in hash_token(token, **FAST)

    @pytest.mark.parametrize("weak", ["short", "password123", "a" * (MIN_TOKEN_LENGTH - 1)])
    def test_rejects_a_token_too_weak_to_be_a_key(self, weak):
        """A short token is a password, and PBKDF2 alone will not save it."""
        with pytest.raises(TokenError, match="at least"):
            hash_token(weak, **FAST)


class TestVerifyToken:
    @pytest.mark.parametrize(
        "record",
        [
            "",
            "nonsense",
            "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA==",
            "pbkdf2_sha256$1000$notbase64!$aGFzaA==",
            "bcrypt$12$abc$def",
            "pbkdf2_sha256$0$c2FsdA==$aGFzaA==",
            "pbkdf2_sha256$1000$$aGFzaA==",
            "pbkdf2_sha256$1000$c2FsdA==$",
        ],
    )
    def test_a_malformed_record_raises_rather_than_guessing(self, record):
        """Silence here would hide a config fault behind a plausible 401."""
        with pytest.raises(TokenError):
            verify_token(generate_token(), record)

    def test_rejects_a_record_hashed_with_a_different_algorithm(self):
        with pytest.raises(TokenError, match="algorithm"):
            verify_token("x" * 32, "scrypt$16384$c2FsdA==$aGFzaA==")


class TestAuthStoreAuthentication:
    def test_resolves_a_configured_token_to_its_principal(self):
        token = generate_token()
        store = _store(clinician=token)

        principal = store.authenticate(token)

        assert principal is not None
        assert principal.role == "clinician"
        assert principal.name == "clinician"

    def test_carries_the_roles_permissions(self):
        token = generate_token()
        store = _store(viewer=token)

        principal = store.authenticate(token)

        assert principal.permissions == frozenset({"sessions:read"})

    def test_rejects_a_token_that_is_not_configured(self):
        store = _store(clinician=generate_token())

        assert store.authenticate(generate_token()) is None

    @pytest.mark.parametrize("presented", [None, "", "  "])
    def test_rejects_an_absent_token(self, presented):
        store = _store(clinician=generate_token())

        assert store.authenticate(presented) is None

    def test_a_malformed_record_never_authenticates(self):
        """A config typo must fail closed, not fall through to authorized."""
        store = AuthStore([("broken", "clinician", "not-a-record")], ROLE_PERMISSIONS)
        token = generate_token()

        assert store.authenticate(token) is None

    def test_an_unknown_role_grants_nothing(self):
        """A role typo in config must not inherit another role's permissions."""
        token = generate_token()
        store = AuthStore([("x", "supeadmin", hash_token(token, **FAST))], ROLE_PERMISSIONS)

        principal = store.authenticate(token)

        assert principal is not None
        assert principal.permissions == frozenset()

    def test_reports_whether_any_principal_exists(self):
        assert _store(clinician=generate_token()).is_configured is True
        assert AuthStore([], ROLE_PERMISSIONS).is_configured is False

    def test_a_verified_token_is_cached_so_the_slow_kdf_runs_once(self, monkeypatch):
        """Every request running a 600k-iteration KDF would be a self-DoS."""
        token = generate_token()
        store = _store(clinician=token)
        store.authenticate(token)

        calls = []
        import sefa.auth as auth

        real = auth.verify_token
        monkeypatch.setattr(
            auth, "verify_token", lambda *a: (calls.append(a[0]), real(*a))[1]
        )
        store.authenticate(token)
        store.authenticate(token)

        assert calls == []

    def test_the_cache_holds_no_plaintext(self):
        token = generate_token()
        store = _store(clinician=token)
        store.authenticate(token)

        assert all(token.encode() not in key for key in store._verified)

    def test_failed_guesses_do_not_grow_the_cache(self):
        """Otherwise a flood of wrong tokens is an unbounded memory DoS."""
        store = _store(clinician=generate_token())

        for _ in range(50):
            assert store.authenticate(generate_token()) is None

        assert store._verified == {}

    def test_the_cache_is_bounded_by_the_number_of_principals(self):
        tokens = {"clinician": generate_token(), "viewer": generate_token()}
        store = _store(**tokens)

        for token in tokens.values():
            store.authenticate(token)

        assert len(store._verified) == len(tokens)


class TestAuthorization:
    def test_grants_a_permission_the_role_carries(self):
        store = _store(viewer=generate_token())
        principal = Principal("v", "viewer", frozenset({"sessions:read"}))

        assert store.authorizes(principal, "sessions:read") is True

    def test_refuses_a_permission_the_role_lacks(self):
        store = _store(viewer=generate_token())
        principal = Principal("v", "viewer", frozenset({"sessions:read"}))

        assert store.authorizes(principal, "calls:place") is False

    def test_refuses_everything_without_a_principal(self):
        store = _store(viewer=generate_token())

        assert store.authorizes(None, "sessions:read") is False

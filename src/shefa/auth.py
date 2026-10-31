"""Bearer-token authentication and role authorization for every route.

The service held transcripts, patient names, and an outbound-call trigger with no
credential at all, so anyone who reached the port could read every patient
conversation and place calls billed to the clinic. This module is the only thing
between an open port and PHI.

Token storage is PBKDF2-HMAC-SHA256 with a per-principal salt, so a leaked config
yields no usable token: an attacker holding every hash still has to run the KDF.
A plain SHA-256 would not, because GPUs make unsalted fast hashes a starting
point rather than a wall.

The KDF is deliberately slow and authn sits on the request path, so each
*verified* token is cached under `sha256(token)` — never the plaintext. Only
successes are cached, which bounds the cache at the number of configured
principals, and means a wrong guess pays full KDF cost on every attempt. That is
the rate limit we want against brute force.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

KDF_ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16

# Below this a token is a password rather than a key, and PBKDF2 is all that
# stands between a leaked config and a cracked credential.
MIN_TOKEN_LENGTH = 24


class TokenError(ValueError):
    """A token hash is malformed, or a token is too weak to accept."""


@dataclass(frozen=True)
class Principal:
    """An authenticated caller and the role it was configured with."""

    name: str
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def generate_token(length: int = 32) -> str:
    """Mint a token with enough entropy that PBKDF2 is the only real barrier."""
    return secrets.token_urlsafe(length)


def hash_token(token: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Return a storable `pbkdf2_sha256$iterations$salt$hash` record."""
    if len(token) < MIN_TOKEN_LENGTH:
        raise TokenError(
            f"token must be at least {MIN_TOKEN_LENGTH} characters; "
            f"got {len(token)}. A short token is a password, not an API key."
        )
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, iterations)
    return "$".join(
        (
            KDF_ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        )
    )


def _parse_record(record: str) -> tuple[int, bytes, bytes]:
    """Parse a stored record, rejecting anything malformed.

    A malformed record raises instead of returning a verdict: a parser that
    shrugged at bad input could report "no match" for a record that should have
    matched, and the operator would be left debugging auth with no signal.
    """
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = record.split("$")
    except ValueError as error:
        raise TokenError(f"malformed token record: {record!r}") from error
    if algorithm != KDF_ALGORITHM:
        raise TokenError(f"unsupported token hash algorithm: {algorithm!r}")
    try:
        iterations = int(raw_iterations)
        salt = base64.b64decode(raw_salt, validate=True)
        digest = base64.b64decode(raw_digest, validate=True)
    except (TypeError, ValueError) as error:
        raise TokenError(f"malformed token record: {record!r}") from error
    if iterations < 1 or not salt or not digest:
        raise TokenError(f"malformed token record: {record!r}")
    return iterations, salt, digest


def verify_token(token: str, record: str) -> bool:
    """Constant-time check of `token` against a stored record."""
    iterations, salt, expected = _parse_record(record)
    candidate = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, iterations)
    return hmac.compare_digest(candidate, expected)


class AuthStore:
    """Resolves a presented bearer token to a `Principal`.

    `principals` is a list of `(name, role, token_record)` triples; `roles` maps
    a role name to the permissions it carries. A role absent from `roles` grants
    nothing, so a typo in the config cannot accidentally widen access.
    """

    def __init__(
        self,
        principals: list[tuple[str, str, str]],
        roles: dict[str, list[str]],
    ) -> None:
        self._principals = list(principals)
        self._roles = {role: frozenset(perms) for role, perms in roles.items()}
        # Verified tokens only, keyed on a hash so no plaintext is retained.
        self._verified: dict[bytes, Principal] = {}

    @property
    def is_configured(self) -> bool:
        """False when no principal can authenticate, which must lock the API."""
        return bool(self._principals)

    def permissions_for(self, role: str) -> frozenset[str]:
        return self._roles.get(role, frozenset())

    def authenticate(self, token: str | None) -> Principal | None:
        """Return the caller for `token`, or None if it matches no principal."""
        if not token:
            return None

        cache_key = hashlib.sha256(token.encode()).digest()
        cached = self._verified.get(cache_key)
        if cached is not None:
            return cached

        for name, role, record in self._principals:
            try:
                matched = verify_token(token, record)
            except TokenError:
                # A malformed record is a config fault, not a credential, and
                # must never be treated as a match.
                continue
            if matched:
                principal = Principal(
                    name=name,
                    role=role,
                    permissions=self.permissions_for(role),
                )
                self._verified[cache_key] = principal
                return principal
        return None

    def principal_named(self, name: str) -> Principal | None:
        """The configured principal for `name`, without authenticating anything.

        Identity here is *claimed*, not proven: this exists for authorizing a
        caller that already entered through real authentication (such as a PHI
        access decision inside an authenticated session). It must never gate a
        request on its own — anyone who knows a name would be anyone.
        """
        for principal_name, role, _record in self._principals:
            if principal_name == name:
                return Principal(
                    name=name, role=role, permissions=self.permissions_for(role)
                )
        return None

    def authorizes(self, principal: Principal | None, permission: str) -> bool:
        """Fail closed: no principal, no permission, no role, no access."""
        if principal is None:
            return False
        return principal.has(permission)

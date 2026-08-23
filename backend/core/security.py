"""Password hashing and session token generation.

argon2id (via argon2-cffi) rather than passlib+bcrypt — argon2id is the
current OWASP-recommended default for new applications, and passlib+bcrypt
has a real-world history of version-compatibility breakage between the two
packages that isn't worth the risk here.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """False for a wrong password, and false (not a crash) for any other
    argon2 error too — e.g. a hash stored in an unexpected format should
    fail closed, not 500. InvalidHashError needs its own except clause: it
    inherits from ValueError, not Argon2Error, despite living in the same
    exceptions module and being exactly the kind of "hash isn't even
    parseable" failure this function is supposed to fail closed on."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (Argon2Error, InvalidHashError):
        return False


def generate_session_token() -> str:
    """High-entropy opaque token stored as the session cookie value and as
    the primary key of UserSession — validity is checked by DB lookup, not
    by decoding/verifying the token itself."""
    return secrets.token_urlsafe(32)

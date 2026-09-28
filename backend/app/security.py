"""Small, dependency-free helpers for team authentication.

Uses hashlib's PBKDF2 (standard library, no extra pip install needed)
instead of bcrypt/passlib so this drops in without touching requirements.txt.
"""
import hashlib
import secrets
import string

_PBKDF2_ITERATIONS = 200_000
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()


def make_password_hash(password: str):
    """Returns (password_hash, salt) for a brand-new password."""
    salt = secrets.token_hex(16)
    return _hash(password, salt), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    if not salt or not expected_hash:
        return False
    # constant-time compare to avoid timing side-channels
    return secrets.compare_digest(_hash(password, salt), expected_hash)


def new_token() -> str:
    """Session secret handed to the frontend after a successful login;
    stored client-side and sent back on every subsequent request to prove
    'you are the same team that registered'."""
    return secrets.token_urlsafe(24)


def new_team_code() -> str:
    """Short, human-shareable public ID, distinct from the free-text team
    name — teams can quote this to organizers without spelling out names."""
    return "MLF-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


# No 0/O/1/I/L so a temporary password read aloud or off a screen isn't misread.
_TEMP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_temp_password() -> str:
    """Readable one-time password an organizer hands to a team that forgot theirs."""
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(8))
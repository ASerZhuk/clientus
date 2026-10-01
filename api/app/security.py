import base64
import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import get_settings

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored: str | None) -> bool:
    """Always spends one argon2 verification, even for unknown users."""
    try:
        return _hasher.verify(stored or _DUMMY_HASH, password) and stored is not None
    except (VerificationError, InvalidHashError):
        return False


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def derived_access_token(tenant_id: int, booking_id: int, idempotency_key: str) -> str:
    """Booking access token that can be re-issued on retry without storing it:
    HMAC(server secret, tenant|booking|idempotency key). Only its hash lives in the DB."""
    msg = f"{tenant_id}:{booking_id}:{idempotency_key}".encode()
    mac = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def client_fingerprint(ip: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), ip.encode(), hashlib.sha256).hexdigest()[:16]


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    return digits

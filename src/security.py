import base64
import hashlib
import hmac
import json
import os
import time

TOKEN_SECRET = os.getenv("HYDROAUTH_SECRET", "hydroagent-local-secret")
TOKEN_TTL_SECONDS = int(os.getenv("HYDROAUTH_TTL_SECONDS", "28800"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return base64.b64encode(salt + pwd_hash).decode()

def check_password(password: str, hashed: str) -> bool:
    data = base64.b64decode(hashed.encode())
    salt, pwd_hash = data[:16], data[16:]
    check_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return hmac.compare_digest(pwd_hash, check_hash)

def create_access_token(subject: str, extra_claims: dict | None = None, expires_in: int = TOKEN_TTL_SECONDS) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
    }
    if extra_claims:
        payload.update(extra_claims)

    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest()
    digest = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{body}.{digest}"


def decode_access_token(token: str) -> dict | None:
    try:
        body, digest = token.split(".", 1)
        expected = base64.urlsafe_b64encode(
            hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(digest, expected):
            return None
        padding = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(f"{body}{padding}".encode()).decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def authenticate(username: str, password: str) -> str | None:
    if username == "user" and password == "password":
        return create_access_token(username, {"roles": ["viewer"]})
    return None


def mask_secret(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:4]}{'*' * (len(normalized) - 8)}{normalized[-4:]}"


__all__ = [
    "authenticate",
    "check_password",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "mask_secret",
]

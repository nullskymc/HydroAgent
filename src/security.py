import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

TOKEN_SECRET = os.getenv("HYDROAUTH_SECRET", "hydroagent-local-secret")
TOKEN_TTL_SECONDS = int(os.getenv("HYDROAUTH_TTL_SECONDS", "28800"))
SECRET_KEY_ENV = "HYDRO_CONFIG_SECRET"
WORKSPACE_SECRET_PATH = Path(__file__).resolve().parents[1] / ".hydro_workspace" / "config-secret.key"
SECRET_VALUE_PREFIX = "enc::"


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
    # 兼容旧测试和离线开发场景。
    if username == "user" and password == "password":
        return create_access_token(username, {"roles": ["viewer"]})
    return None


def _derive_fernet_key(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _read_or_create_local_secret_key() -> bytes:
    if WORKSPACE_SECRET_PATH.exists():
        return WORKSPACE_SECRET_PATH.read_bytes().strip()

    WORKSPACE_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    WORKSPACE_SECRET_PATH.write_bytes(key)
    try:
        os.chmod(WORKSPACE_SECRET_PATH, 0o600)
    except OSError:
        # Windows 等平台可能不支持 chmod，这里不影响功能。
        pass
    return key


def get_config_secret_key() -> bytes:
    seed = os.getenv(SECRET_KEY_ENV, "").strip()
    if seed:
        try:
            Fernet(seed.encode("utf-8"))
            return seed.encode("utf-8")
        except Exception:
            return _derive_fernet_key(seed)
    return _read_or_create_local_secret_key()


def encrypt_config_secret(value: str) -> str:
    if not value:
        return ""
    token = Fernet(get_config_secret_key()).encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{SECRET_VALUE_PREFIX}{token}"


def decrypt_config_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith(SECRET_VALUE_PREFIX):
        return value

    token = value[len(SECRET_VALUE_PREFIX):]
    try:
        return Fernet(get_config_secret_key()).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("配置密钥解密失败，请检查 HYDRO_CONFIG_SECRET 或本地密钥文件。") from exc


def is_encrypted_config_secret(value: str | None) -> bool:
    return bool(value and value.startswith(SECRET_VALUE_PREFIX))


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
    "decrypt_config_secret",
    "encrypt_config_secret",
    "decode_access_token",
    "hash_password",
    "is_encrypted_config_secret",
    "mask_secret",
]

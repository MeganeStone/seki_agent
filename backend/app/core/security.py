import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings


def hash_password(password: str, salt: bytes | None = None) -> str:
    """使用 PBKDF2-HMAC-SHA256 哈希密码。

    返回格式为 `salt$digest`，不依赖额外认证库，方便当前内部工具快速落地。
    生产环境如接入统一身份系统，可在 AuthService 边界替换实现。
    """
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_value: str) -> bool:
    """校验明文密码和数据库中的哈希值。"""
    try:
        salt_hex, digest_hex = stored_value.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(actual, expected)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _sign(message: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256)
    return _b64url_encode(signature.digest())


def create_access_token(subject: str) -> str:
    """创建一个轻量自签名访问 token。

    当前 token 结构类似 JWT，但只包含 payload.signature 两段；对内部工具足够简单。
    如后续接入 OAuth/JWT 标准库，可以保持外层 Bearer 认证契约不变。
    """
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(encoded_payload, settings.token_secret_key)
    return f"{encoded_payload}.{signature}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析并校验访问 token，失败时统一返回 None。"""
    settings = get_settings()
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = _sign(encoded_payload, settings.token_secret_key)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        return None
    if datetime.now(timezone.utc).timestamp() > expires_at:
        return None

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        return None

    return payload

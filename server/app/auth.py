"""登录口令 -> HMAC 签名 token（无第三方依赖）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict, deque

from .config import get_settings


class AuthError(Exception):
    pass


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64e(mac)


def issue_token() -> tuple[str, int]:
    """返回 (token, expires_at_unix)。"""
    s = get_settings()
    exp = int(time.time()) + s.token_ttl
    payload_b64 = _b64e(json.dumps({"exp": exp}, separators=(",", ":")).encode())
    return f"v1.{payload_b64}.{_sign(payload_b64, s.token_secret)}", exp


def verify_token(token: str) -> None:
    """校验 token，失败抛 AuthError。"""
    s = get_settings()
    try:
        ver, payload_b64, sig = token.strip().split(".")
        if ver != "v1":
            raise ValueError
        if not hmac.compare_digest(sig, _sign(payload_b64, s.token_secret)):
            raise ValueError
        payload = json.loads(_b64d(payload_b64))
        if int(payload["exp"]) < time.time():
            raise AuthError("token 已过期")
    except AuthError:
        raise
    except Exception:
        raise AuthError("无效 token")


def check_password(password: str) -> bool:
    s = get_settings()
    return hmac.compare_digest(password.encode(), s.password.encode())


# ── 登录限速（进程内，单用户场景足够）─────────────────────────
_attempts: dict[str, deque[float]] = defaultdict(deque)


def login_allowed(ip: str) -> bool:
    s = get_settings()
    now = time.time()
    q = _attempts[ip]
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= s.login_rate_limit:
        return False
    q.append(now)
    return True

"""运行配置：全部来自环境变量。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _parse_ttl(raw: str) -> int:
    """解析 '72h' / '30d' / '15m' / '900'（秒）。"""
    raw = raw.strip()
    m = re.fullmatch(r"(\d+)\s*([smhd]?)", raw, re.I)
    if not m:
        raise ValueError(f"无法解析 TTL: {raw!r}")
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _bool(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    root: Path                 # 笔记本根目录
    password: str              # 登录口令（明文）
    token_secret: str          # token 签名密钥
    token_ttl: int             # token 有效期（秒）
    auto_write: bool           # AI 全局免确认写入
    llm_base_url: str          # OpenAI 兼容接口
    llm_api_key: str
    llm_model: str
    login_rate_limit: int      # 每分钟每 IP 允许登录尝试次数


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    password = os.environ.get("NOTE_MD_PASSWORD", "")
    secret = os.environ.get("NOTE_MD_TOKEN_SECRET") or f"dev-{password or 'note-md'}"
    return Settings(
        root=Path(os.environ.get("NOTE_MD_ROOT", "/notes")).resolve(),
        password=password,
        token_secret=secret,
        token_ttl=_parse_ttl(os.environ.get("NOTE_MD_TOKEN_TTL", "72h")),
        auto_write=_bool(os.environ.get("NOTE_MD_AI_AUTO_WRITE")),
        llm_base_url=os.environ.get("OPENAI_BASE_URL", "").rstrip("/"),
        llm_api_key=os.environ.get("OPENAI_API_KEY", ""),
        llm_model=os.environ.get("OPENAI_MODEL", ""),
        login_rate_limit=int(os.environ.get("NOTE_MD_LOGIN_RATE", "5")),
    )

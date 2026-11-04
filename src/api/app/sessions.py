"""AI 会话记录：<root>/.agents/sessions/<id>.md

格式（人机皆可读）：
    # <title>
    _2025-11-03 19:20_

    ## user
    ...

    ## assistant
    ...
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .config import get_settings


def _sessions_dir() -> Path:
    d = get_settings().root / ".agents" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


_SAFE = re.compile(r"[^\w\u4e00-\u9fff-]")


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + _SAFE.sub("", _title_seed())[:20]


def _title_seed() -> str:
    return ""


def session_file(session_id: str) -> Path:
    if not re.fullmatch(r"[\w-]+", session_id or ""):
        raise ValueError("非法 session id")
    return _sessions_dir() / f"{session_id}.md"


def create_session(session_id: str, first_message: str) -> None:
    title = first_message.strip().splitlines()[0][:40] if first_message.strip() else "新会话"
    f = session_file(session_id)
    if not f.exists():
        f.write_text(f"# {title}\n\n_{time.strftime('%Y-%m-%d %H:%M')}_\n\n", "utf-8")


def append_message(session_id: str, role: str, content: str) -> None:
    f = session_file(session_id)
    label = {"user": "user", "assistant": "assistant"}.get(role, role)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"## {label}\n\n{content.strip()}\n\n")


def append_tool_note(session_id: str, note: str) -> None:
    f = session_file(session_id)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"> tool: {note.strip()}\n\n")


def load_messages(session_id: str) -> list[dict]:
    """从会话文件恢复 user/assistant 消息（工具细节不进上下文）。"""
    f = session_file(session_id)
    if not f.exists():
        return []
    msgs: list[dict] = []
    role, buf = None, []
    for line in f.read_text("utf-8").splitlines():
        m = re.fullmatch(r"## (user|assistant)", line.strip())
        if m:
            if role and buf:
                msgs.append({"role": role, "content": "\n".join(buf).strip()})
            role, buf = m.group(1), []
        elif role is not None:
            buf.append(line)
    if role and buf:
        msgs.append({"role": role, "content": "\n".join(buf).strip()})
    return [m for m in msgs if m["content"]]


def list_sessions() -> list[dict]:
    out = []
    for f in sorted(_sessions_dir().glob("*.md"), reverse=True):
        head = f.read_text("utf-8").splitlines()[:1]
        title = head[0].lstrip("# ").strip() if head else f.stem
        st = f.stat()
        out.append({"id": f.stem, "title": title or f.stem,
                    "mtime": st.st_mtime, "size": st.st_size})
    return out


def read_session(session_id: str) -> str:
    f = session_file(session_id)
    if not f.exists():
        raise FileNotFoundError(session_id)
    return f.read_text("utf-8")

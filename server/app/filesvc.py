"""核心文件服务：REST 与 MCP 共用。

约定：
- 一切路径相对笔记本根目录，resolve 后必须仍在根内；
- 只管理 *.md；隐藏目录（. 开头，如 .agents/ .trash/）不对常规接口暴露；
- 删除 = 移入 .trash/（保留相对路径结构，文件名前加时间戳防冲突）。
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

from .config import get_settings


class FileError(Exception):
    status = 400


class NotFound(FileError):
    status = 404


class Conflict(FileError):
    status = 409


class InvalidPath(FileError):
    status = 400


_CTRL = re.compile(r"[\x00-\x1f]")


def resolve_path(rel: str, *, must_exist: bool = False) -> Path:
    """把相对路径安全地解析到根目录下。"""
    s = get_settings()
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel or rel == ".":
        target = s.root
    else:
        if _CTRL.search(rel) or rel.startswith("/") or ".." in rel.split("/"):
            raise InvalidPath(f"非法路径: {rel!r}")
        target = (s.root / rel).resolve()
        try:
            target.relative_to(s.root)
        except ValueError:
            raise InvalidPath(f"路径越界: {rel!r}")
    if any(part.startswith(".") for part in target.relative_to(s.root).parts):
        raise InvalidPath("隐藏目录不可访问")
    if must_exist and not target.exists():
        raise NotFound(f"不存在: {rel}")
    return target


def _rel(path: Path) -> str:
    return path.relative_to(get_settings().root).as_posix()


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _is_md(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() == ".md"


# ── 目录树 ────────────────────────────────────────────────
def get_tree(rel: str = "", depth: int = 10) -> "dict":
    base = resolve_path(rel, must_exist=True)
    return _node(base, depth)


def _node(p: Path, depth: int) -> dict:
    st = p.stat()
    if p.is_dir():
        children = None
        if depth > 0:
            entries = [e for e in p.iterdir()
                       if not e.name.startswith(".") and (e.is_dir() or _is_md(e))]
            entries.sort(key=lambda e: (e.is_file(), e.name.lower()))
            children = [_node(e, depth - 1) for e in entries]
        return {"name": p.name or "笔记本", "path": _rel(p) if p != get_settings().root else "",
                "type": "dir", "mtime": st.st_mtime, "size": 0, "children": children}
    return {"name": p.name, "path": _rel(p), "type": "file",
            "mtime": st.st_mtime, "size": st.st_size, "children": None}


# ── 读写 ──────────────────────────────────────────────────
def read_file(rel: str, offset: int = 0, limit: int | None = None) -> dict:
    p = resolve_path(rel, must_exist=True)
    if not _is_md(p):
        raise InvalidPath("仅支持 .md 文件")
    content = p.read_text("utf-8")
    st = p.stat()
    if limit is not None:
        lines = content.splitlines(keepends=True)
        content = "".join(lines[offset:offset + limit])
    return {"path": _rel(p), "content": content,
            "hash": compute_hash(p.read_text("utf-8")),
            "mtime": st.st_mtime, "size": st.st_size}


def write_file(rel: str, content: str, base_hash: str | None = None) -> dict:
    p = resolve_path(rel)
    if p.suffix.lower() != ".md":
        raise InvalidPath("仅支持 .md 文件")
    if p.exists():
        if not _is_md(p):
            raise Conflict(f"目标不是 .md 文件: {rel}")
        if base_hash is not None:
            current = compute_hash(p.read_text("utf-8"))
            if current != base_hash:
                raise Conflict("文件已被修改（hash 不匹配）")
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, content)
    st = p.stat()
    return {"path": _rel(p), "hash": compute_hash(content),
            "mtime": st.st_mtime, "size": st.st_size}


def _atomic_write(p: Path, content: str) -> None:
    tmp = p.with_name(f".{p.name}.tmp-{os.getpid()}")
    tmp.write_text(content, "utf-8")
    os.replace(tmp, p)


def create(rel: str, kind: str = "file", content: str = "") -> dict:
    p = resolve_path(rel)
    if p.exists():
        raise Conflict(f"已存在: {rel}")
    if kind == "dir":
        p.mkdir(parents=True)
    else:
        if p.suffix.lower() != ".md":
            raise InvalidPath("仅支持 .md 文件")
        p.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(p, content)
    return _node(p, 0)


def move(src: str, dst: str) -> dict:
    sp = resolve_path(src, must_exist=True)
    dp = resolve_path(dst)
    if dp.exists():
        raise Conflict(f"目标已存在: {dst}")
    if sp.is_file() and dp.suffix.lower() != ".md":
        raise InvalidPath("仅支持 .md 文件")
    dp.parent.mkdir(parents=True, exist_ok=True)
    sp.rename(dp)
    return _node(dp, 0)


def trash(rel: str) -> dict:
    """删除 = 移入 .trash/（保留目录结构）。"""
    p = resolve_path(rel, must_exist=True)
    root = get_settings().root
    trash_dir = root / ".trash"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = trash_dir / stamp / p.relative_to(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    p.rename(dest)
    if p.parent != root and not any(p.parent.iterdir()):
        p.parent.rmdir()
    return {"path": _rel(p), "trashed_to": dest.relative_to(root).as_posix()}

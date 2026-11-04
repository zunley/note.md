"""全文搜索：v1 自实现遍历（目录规模小）。"""
from __future__ import annotations

import re

from .config import get_settings
from .filesvc import _is_md  # 复用判定


def search(query: str, glob: str = "", regex: bool = False,
           max_hits: int = 200) -> list[dict]:
    root = get_settings().root
    if not query:
        return []
    try:
        pat = re.compile(query if regex else re.escape(query),
                         0 if regex else re.I)
    except re.error as e:
        raise ValueError(f"正则错误: {e}")

    hits: list[dict] = []
    suffix = glob.strip().lstrip("*") if glob else ".md"
    for p in sorted(root.rglob("*.md") if suffix == ".md" else root.rglob(f"*{suffix}")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        if not _is_md(p):
            continue
        try:
            lines = p.read_text("utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(lines, 1):
            m = pat.search(line)
            if m:
                hits.append({"path": p.relative_to(root).as_posix(),
                             "line": i,
                             "text": line.strip()[:200],
                             "column": m.start()})
                if len(hits) >= max_hits:
                    return hits
    return hits


def list_backlinks(rel: str) -> list[dict]:
    """谁引用了这个笔记：匹配指向该文件的 markdown 链接。"""
    root = get_settings().root
    target = rel.strip().replace("\\", "/").lstrip("/")
    name = target.rsplit("/", 1)[-1]
    stem = name[:-3] if name.endswith(".md") else name
    pat = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    out: list[dict] = []
    for p in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        try:
            lines = p.read_text("utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel_p = p.relative_to(root).as_posix()
        if rel_p == target:
            continue
        for i, line in enumerate(lines, 1):
            for m in pat.finditer(line):
                link = m.group(1).split("#")[0].strip()
                if not link.endswith(".md"):
                    continue
                # 相对当前文件解析
                resolved = (p.parent / link).resolve()
                try:
                    resolved_rel = resolved.relative_to(root).as_posix()
                except ValueError:
                    continue
                if resolved_rel == target or link.rsplit("/", 1)[-1] == name \
                        or link.rsplit("/", 1)[-1] == f"{stem}.md":
                    out.append({"path": rel_p, "line": i,
                                "text": line.strip()[:200], "column": m.start()})
                    break
    return out

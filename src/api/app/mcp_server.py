"""FastMCP server：文件读写/查找工具（薄封装 filesvc/search/sessions）。

- 进程内 Agent 直接调用底层函数（见 agent.TOOLS）；
- 外部 MCP 客户端经 streamable-http 接入（/mcp，带 token）。
"""
from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from . import filesvc, search as search_mod, sessions as sess_mod

mcp = FastMCP(
    name="note-md",
    instructions="个人 Markdown 笔记本工具：所有路径相对于笔记本根目录，仅 .md 文件。",
)


@mcp.tool
def list_tree(path: str = "", depth: int = 3) -> dict[str, Any]:
    """列出笔记本目录树（仅 .md 文件与目录）。path 相对根目录，空为根。"""
    return filesvc.get_tree(path, depth)


@mcp.tool
def read_file(path: str, offset: int = 0, limit: int | None = None) -> dict[str, Any]:
    """读取 .md 文件内容。offset/limit 按行分段（大文件用）。"""
    return filesvc.read_file(path, offset, limit)


@mcp.tool
def search_files(query: str, glob: str = "", regex: bool = False) -> list[dict[str, Any]]:
    """全文检索笔记本，返回 文件:行号 + 上下文。regex=True 时 query 为正则。"""
    return search_mod.search(query, glob, regex)


@mcp.tool
def list_backlinks(path: str) -> list[dict[str, Any]]:
    """查找引用了指定笔记的其他笔记（markdown 链接反链）。"""
    return search_mod.list_backlinks(path)


@mcp.tool
def get_outline(path: str) -> list[dict[str, Any]]:
    """提取笔记标题大纲（level/标题/行号），用于内容概览与摘要。"""
    import re
    content = filesvc.read_file(path)["content"]
    out = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            out.append({"level": len(m.group(1)), "text": m.group(2).strip(), "line": i})
    return out


@mcp.tool
def create_file(path: str, content: str = "") -> dict[str, Any]:
    """新建 .md 文件（已存在则报错）。content 可选。"""
    return filesvc.create(path, "file", content)


@mcp.tool
def write_file(path: str, content: str, base_hash: str | None = None) -> dict[str, Any]:
    """覆盖写入 .md 文件。base_hash 提供时做乐观锁（不匹配则拒绝）。"""
    return filesvc.write_file(path, content, base_hash)


@mcp.tool
def append_file(path: str, content: str) -> dict[str, Any]:
    """向 .md 文件末尾追加内容（速记/日志场景）。"""
    current = ""
    try:
        current = filesvc.read_file(path)["content"]
    except filesvc.NotFound:
        pass
    return filesvc.write_file(path, current + content)


@mcp.tool
def move_file(src: str, dst: str) -> dict[str, Any]:
    """移动/重命名文件或目录。dst 为新路径（含文件名）。"""
    return filesvc.move(src, dst)


@mcp.tool
def delete_file(path: str) -> dict[str, Any]:
    """删除文件/目录（移入 .trash/ 回收站，可人工找回）。"""
    return filesvc.trash(path)


@mcp.tool
def list_sessions() -> list[dict[str, Any]]:
    """列出历史 AI 会话记录。"""
    return sess_mod.list_sessions()


@mcp.tool
def read_session(session_id: str) -> str:
    """读取某个历史 AI 会话的完整记录（Markdown）。"""
    return sess_mod.read_session(session_id)

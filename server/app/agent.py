"""LLM 运行时：OpenAI 兼容接口 + 工具调用循环，产出 SSE 事件流。

事件（dict，main.py 序列化为 SSE）：
  {"type":"session","id"} / {"type":"token","text"} / {"type":"tool_call","id","name","args"}
  {"type":"tool_result","id","ok","summary"} / {"type":"error","message"} / {"type":"done"}
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from . import filesvc, search as search_mod, sessions as sess_mod
from .config import get_settings

SYSTEM_PROMPT = """\
你是 note.md —— 个人 Markdown 笔记本的内置助手。笔记本里全是 .md 文件，路径相对根目录。

原则：
- 动手前先了解：用 search_files / read_file / list_tree 查看现状，再修改；
- 文件操作工具直接生效：create_file / write_file / append_file / move_file / delete_file（删除进回收站）；
- 若工具返回「未授权写入」，请告知用户在聊天窗开启写入授权，不要反复重试；
- 回答简洁，引用文件路径时用 `路径.md` 形式；
- 修改文件后简述改了什么。"""

# ── 工具定义（给 LLM 的 JSON schema）──────────────────────────
_WRITE_TOOLS = {"create_file", "write_file", "append_file", "move_file", "delete_file"}

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "list_tree",
        "description": "列出笔记本目录树（仅 .md 与目录）",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "相对根目录的路径，空为根"},
            "depth": {"type": "integer", "description": "展开深度，默认 3"}}}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取 .md 文件内容",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "起始行（0-based）"},
            "limit": {"type": "integer", "description": "读取行数"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "全文检索，返回 文件:行号 + 上下文",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "regex": {"type": "boolean", "description": "query 是否为正则"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "list_backlinks",
        "description": "查找引用了指定笔记的其他笔记",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "get_outline",
        "description": "提取笔记标题大纲",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "create_file",
        "description": "新建 .md 文件",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "覆盖写入 .md 文件（整文件替换）",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "append_file",
        "description": "向 .md 文件末尾追加内容",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "move_file",
        "description": "移动/重命名文件或目录",
        "parameters": {"type": "object", "properties": {
            "src": {"type": "string"}, "dst": {"type": "string"}},
            "required": ["src", "dst"]}}},
    {"type": "function", "function": {
        "name": "delete_file",
        "description": "删除文件/目录（移入回收站）",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_sessions",
        "description": "列出历史 AI 会话记录",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_session",
        "description": "读取某个历史 AI 会话记录",
        "parameters": {"type": "object", "properties": {
            "session_id": {"type": "string"}}, "required": ["session_id"]}}},
]


def _outline(path: str) -> list[dict[str, Any]]:
    import re
    content = filesvc.read_file(path)["content"]
    out = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            out.append({"level": len(m.group(1)), "text": m.group(2).strip(), "line": i})
    return out


def _summarize(name: str, args: dict, result: Any) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"{name} 失败：{result['error']}"
    if name == "search_files":
        return f'search_files("{args.get("query", "")}") → {len(result)} 处命中'
    if name in ("read_file", "get_outline", "list_backlinks"):
        return f'{name}({args.get("path", "")})'
    if name == "list_tree":
        return f'list_tree({args.get("path") or "根目录"})'
    if name == "write_file":
        return f'write_file({args.get("path")}, {len(args.get("content", ""))} 字)'
    if name == "create_file":
        return f'create_file({args.get("path")})'
    if name == "append_file":
        return f'append_file({args.get("path")})'
    if name == "move_file":
        return f'move_file({args.get("src")} → {args.get("dst")})'
    if name == "delete_file":
        return f'delete_file({args.get("path")})'
    return name


def _execute(name: str, args: dict, allow_write: bool) -> Any:
    try:
        if name in _WRITE_TOOLS and not allow_write and not get_settings().auto_write:
            return {"error": "本会话未授权写入，请提示用户在聊天窗开启写入授权"}
        if name == "list_tree":
            return filesvc.get_tree(args.get("path", ""), int(args.get("depth", 3)))
        if name == "read_file":
            return filesvc.read_file(args["path"], int(args.get("offset", 0)),
                                     args.get("limit"))
        if name == "search_files":
            return search_mod.search(args["query"], regex=bool(args.get("regex")))
        if name == "list_backlinks":
            return search_mod.list_backlinks(args["path"])
        if name == "get_outline":
            return _outline(args["path"])
        if name == "create_file":
            return filesvc.create(args["path"], "file", args.get("content", ""))
        if name == "write_file":
            return filesvc.write_file(args["path"], args["content"])
        if name == "append_file":
            return filesvc_write_append(args["path"], args["content"])
        if name == "move_file":
            return filesvc.move(args["src"], args["dst"])
        if name == "delete_file":
            return filesvc.trash(args["path"])
        if name == "list_sessions":
            return sess_mod.list_sessions()
        if name == "read_session":
            return {"content": sess_mod.read_session(args["session_id"])}
        return {"error": f"未知工具 {name}"}
    except Exception as e:  # 工具错误回传给 LLM，不中断会话
        return {"error": str(e)}


def filesvc_write_append(path: str, content: str) -> dict:
    try:
        current = filesvc.read_file(path)["content"]
    except filesvc.NotFound:
        current = ""
    return filesvc.write_file(path, current + content)


# ── 会话上下文缓存（含工具消息；md 落盘只存人话）─────────────
_cache: dict[str, list[dict]] = {}


def _history(session_id: str) -> list[dict]:
    if session_id not in _cache:
        _cache[session_id] = sess_mod.load_messages(session_id)
    return _cache[session_id]


async def run_chat(message: str, session_id: str, allow_write: bool) -> AsyncIterator[dict]:
    s = get_settings()
    if not s.llm_base_url or not s.llm_model:
        yield {"type": "error", "message": "未配置 LLM（OPENAI_BASE_URL / OPENAI_MODEL）"}
        yield {"type": "done"}
        return

    new = not sess_mod.session_file(session_id).exists()
    if new:
        sess_mod.create_session(session_id, message)
    yield {"type": "session", "id": session_id}

    hist = _history(session_id)
    hist.append({"role": "user", "content": message})
    sess_mod.append_message(session_id, "user", message)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *hist]

    try:
        for _ in range(8):  # 工具循环上限
            assistant: dict = {"role": "assistant", "content": ""}
            tool_calls: dict[int, dict] = {}
            async for ev in _stream_completion(s, messages, assistant, tool_calls):
                yield ev

            if not tool_calls:
                if assistant["content"]:
                    hist.append({"role": "assistant", "content": assistant["content"]})
                    sess_mod.append_message(session_id, "assistant", assistant["content"])
                yield {"type": "done"}
                return

            # 执行工具
            messages.append({**assistant, "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["args_json"]}}
                for tc in tool_calls.values()]})
            for tc in tool_calls.values():
                try:
                    args = json.loads(tc["args_json"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _execute(tc["name"], args, allow_write)
                ok = not (isinstance(result, dict) and result.get("error"))
                summary = _summarize(tc["name"], args, result)
                yield {"type": "tool_call", "id": tc["id"], "name": tc["name"], "args": args}
                yield {"type": "tool_result", "id": tc["id"], "ok": ok,
                       "summary": summary,
                       "error": (result or {}).get("error") if isinstance(result, dict) else None}
                sess_mod.append_tool_note(session_id, summary)
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps(result, ensure_ascii=False, default=str)[:8000]})
        yield {"type": "error", "message": "工具调用轮次过多，已停止"}
    except httpx.HTTPError as e:
        yield {"type": "error", "message": f"LLM 请求失败: {e}"}
    yield {"type": "done"}


async def _stream_completion(s, messages, assistant: dict,
                             tool_calls: dict) -> AsyncIterator[dict]:
    """流式调用 chat/completions，产出 token 事件，填充 assistant/tool_calls。"""
    payload = {"model": s.llm_model, "messages": messages, "tools": TOOLS,
               "stream": True, "temperature": 0.4}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
        async with client.stream(
            "POST", f"{s.llm_base_url}/chat/completions", json=payload,
            headers={"Authorization": f"Bearer {s.llm_api_key}"},
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")[:300]
                yield {"type": "error", "message": f"LLM {resp.status_code}: {body}"}
                return
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta.get("content"):
                    assistant["content"] += delta["content"]
                    yield {"type": "token", "text": delta["content"]}
                for tcd in delta.get("tool_calls") or []:
                    idx = tcd.get("index", 0)
                    tc = tool_calls.setdefault(idx, {"id": "", "name": "", "args_json": ""})
                    if tcd.get("id"):
                        tc["id"] = tcd["id"]
                    fn = tcd.get("function") or {}
                    if fn.get("name"):
                        tc["name"] = fn["name"]
                    if fn.get("arguments"):
                        tc["args_json"] += fn["arguments"]

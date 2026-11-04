"""FastAPI 入口：REST API + MCP 挂载 + 静态资源（前端构建产物）。"""
from __future__ import annotations

import json
import time
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agent, auth, filesvc, search as search_mod, sessions as sess_mod
from .config import get_settings
from .mcp_server import mcp
from .models import ChatReq, CreateReq, LoginReq, LoginResp, MoveReq, WriteReq

mcp_asgi = mcp.http_app(path="/")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """显式进入 MCP 子应用的 lifespan（session manager 等）。"""
    async with AsyncExitStack() as stack:
        lifespan_fn = getattr(mcp_asgi, "lifespan", None)
        if lifespan_fn is not None:
            await stack.enter_async_context(lifespan_fn(mcp_asgi))
        yield


app = FastAPI(title="note.md", docs_url=None, redoc_url=None, lifespan=_lifespan)


# ── 鉴权 ──────────────────────────────────────────────────
def require_token(request: Request) -> None:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        token = request.query_params.get("token", "")
    try:
        auth.verify_token(token)
    except auth.AuthError as e:
        raise HTTPException(401, str(e))


@app.post("/api/auth/login", response_model=LoginResp)
def login(req: LoginReq, request: Request):
    ip = request.client.host if request.client else "?"
    if not auth.login_allowed(ip):
        raise HTTPException(429, "尝试过于频繁，请稍后再试")
    if not auth.check_password(req.password):
        raise HTTPException(401, "口令错误")
    token, exp = auth.issue_token()
    return LoginResp(token=token, expires_at=exp)


@app.post("/api/auth/refresh", response_model=LoginResp)
def refresh(_: None = Depends(require_token)):
    token, exp = auth.issue_token()
    return LoginResp(token=token, expires_at=exp)


@app.get("/api/health")
def health():
    return {"ok": True, "root": str(get_settings().root)}


# ── 文件 ──────────────────────────────────────────────────
@app.get("/api/files/tree")
def api_tree(path: str = "", depth: int = 10, _=Depends(require_token)):
    try:
        return filesvc.get_tree(path, depth)
    except filesvc.FileError as e:
        raise HTTPException(e.status, str(e))


@app.get("/api/files/content")
def api_read(path: str, _=Depends(require_token)):
    try:
        return filesvc.read_file(path)
    except filesvc.FileError as e:
        raise HTTPException(e.status, str(e))


@app.put("/api/files/content")
def api_write(req: WriteReq, _=Depends(require_token)):
    try:
        return filesvc.write_file(req.path, req.content, req.base_hash)
    except filesvc.FileError as e:
        raise HTTPException(e.status, str(e))


@app.post("/api/files")
def api_create(req: CreateReq, _=Depends(require_token)):
    try:
        return filesvc.create(req.path, req.type, req.content)
    except filesvc.FileError as e:
        raise HTTPException(e.status, str(e))


@app.post("/api/files/move")
def api_move(req: MoveReq, _=Depends(require_token)):
    try:
        return filesvc.move(req.src, req.dst)
    except filesvc.FileError as e:
        raise HTTPException(e.status, str(e))


@app.delete("/api/files")
def api_delete(path: str, _=Depends(require_token)):
    try:
        return filesvc.trash(path)
    except filesvc.FileError as e:
        raise HTTPException(e.status, str(e))


# ── 搜索 / 会话 ───────────────────────────────────────────
@app.get("/api/search")
def api_search(q: str, regex: bool = False, _=Depends(require_token)):
    try:
        return {"hits": search_mod.search(q, regex=regex)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/sessions")
def api_sessions(_=Depends(require_token)):
    return sess_mod.list_sessions()


@app.get("/api/sessions/{session_id}")
def api_session(session_id: str, _=Depends(require_token)):
    try:
        return {"id": session_id, "content": sess_mod.read_session(session_id)}
    except FileNotFoundError:
        raise HTTPException(404, "会话不存在")


# ── AI 聊天（SSE）────────────────────────────────────────
@app.post("/api/chat")
async def api_chat(req: ChatReq, _=Depends(require_token)):
    session_id = req.session_id or time.strftime("%Y%m%d-%H%M%S") + "-chat"

    async def gen():
        async for ev in agent.run_chat(req.message, session_id, req.allow_write):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── MCP（streamable-http，鉴权包装）──────────────────────
class MCPAuth:
    """鉴权 + 路径归一化（MCP 端点固定在 /mcp，内部路由为 /）。"""

    def __init__(self, asgi_app):
        self.inner = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from urllib.parse import parse_qs
            headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
            token = headers.get("authorization", "")
            token = token[7:] if token.lower().startswith("bearer ") else ""
            token = token or parse_qs(scope.get("query_string", b"").decode()).get("token", [""])[0]
            try:
                auth.verify_token(token)
            except auth.AuthError:
                await JSONResponse({"detail": "Unauthorized"}, 401)(scope, receive, send)
                return
            scope = dict(scope)
            scope["path"] = "/"
            scope["root_path"] = scope.get("root_path", "") + "/mcp"
        await self.inner(scope, receive, send)


mcp_authed = MCPAuth(mcp_asgi)
app.mount("/mcp", mcp_authed)
# Starlette 的 Mount 不匹配裸路径，补一条精确路由
app.add_route("/mcp", mcp_authed, methods=["GET", "POST", "DELETE"])


# ── 静态资源（前端构建产物）───────────────────────────────
DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(DIST)):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_frontend():
        return JSONResponse({"detail": "前端未构建（web/dist 不存在）"}, 503)

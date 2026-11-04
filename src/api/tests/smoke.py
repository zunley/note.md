"""后端冒烟测试：python tests/smoke.py"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp(prefix="note-md-test-")
os.environ.update({
    "NOTE_MD_ROOT": tmp,
    "NOTE_MD_PASSWORD": "test123",
    "NOTE_MD_TOKEN_SECRET": "smoke",
    "NOTE_MD_TOKEN_TTL": "1h",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
c.__enter__()  # 显式启动应用 lifespan（含 MCP session manager）
ok = 0


def check(name: str, cond: bool, extra=""):
    global ok
    print(("✓" if cond else "✗"), name, extra if not cond else "")
    if cond:
        ok += 1
    else:
        raise SystemExit(f"FAILED: {name} {extra}")


# ── 鉴权 ──────────────────────────────────────────────────
r = c.get("/api/files/tree")
check("未带 token 返回 401", r.status_code == 401)

r = c.post("/api/auth/login", json={"password": "wrong"})
check("错误口令 401", r.status_code == 401)

r = c.post("/api/auth/login", json={"password": "test123"})
check("登录成功", r.status_code == 200)
token = r.json()["token"]
H = {"Authorization": f"Bearer {token}"}

# ── 文件 CRUD ─────────────────────────────────────────────
r = c.post("/api/files", json={"path": "brain/记忆.md", "content": "# 记忆\n\nhello"},
           headers=H)
check("新建文件", r.status_code == 200, r.text)

r = c.post("/api/files", json={"path": "brain/记忆.md"}, headers=H)
check("重复创建 409", r.status_code == 409)

r = c.get("/api/files/content", params={"path": "brain/记忆.md"}, headers=H)
check("读取文件", r.status_code == 200 and r.json()["content"].startswith("# 记忆"))
h = r.json()["hash"]

r = c.put("/api/files/content", json={"path": "brain/记忆.md", "content": "# 记忆\n\nv2",
                                      "base_hash": h}, headers=H)
check("带 hash 保存成功", r.status_code == 200)
h2 = r.json()["hash"]

r = c.put("/api/files/content", json={"path": "brain/记忆.md", "content": "stale",
                                      "base_hash": h}, headers=H)
check("过期 hash 409", r.status_code == 409)

r = c.put("/api/files/content", json={"path": "brain/记忆.md", "content": "# 记忆\n\nv3"},
          headers=H)
check("无 hash 直接覆盖", r.status_code == 200)

r = c.post("/api/files", json={"path": "projects", "type": "dir"}, headers=H)
check("新建目录", r.status_code == 200)

r = c.post("/api/files/move", json={"src": "brain/记忆.md", "dst": "projects/记忆.md"},
           headers=H)
check("移动文件", r.status_code == 200)

r = c.get("/api/files/tree", headers=H)
tree = r.json()
names = [ch["name"] for ch in tree["children"]]
check("目录树包含 projects", "projects" in names and "brain" in names, tree)
check("目录树不列非 md 文件", all(ch["type"] in ("dir", "file") for ch in tree["children"]))

# 隐藏目录与路径穿越
r = c.get("/api/files/content", params={"path": "../etc/passwd"}, headers=H)
check("路径穿越被拒", r.status_code == 400)
r = c.get("/api/files/content", params={"path": ".agents/sessions/x.md"}, headers=H)
check("隐藏目录被拒", r.status_code == 400)

# ── 删除进回收站 ──────────────────────────────────────────
r = c.delete("/api/files", params={"path": "projects/记忆.md"}, headers=H)
check("删除文件", r.status_code == 200 and r.json()["trashed_to"].startswith(".trash/"))
trash_path = Path(tmp) / r.json()["trashed_to"]
check("回收站可找回", trash_path.exists())

# ── 搜索 / 反链 ───────────────────────────────────────────
c.post("/api/files", json={"path": "a.md", "content": "指向 [记忆](projects/记忆.md) 的链接"},
       headers=H)
c.post("/api/files", json={"path": "projects/记忆.md", "content": "# 记忆\n容器挂载即笔记本"},
       headers=H)
r = c.get("/api/search", params={"q": "容器挂载"}, headers=H)
check("全文搜索命中", r.status_code == 200 and len(r.json()["hits"]) == 1)

r = c.get("/api/files/content", params={"path": "projects/记忆.md"}, headers=H)
from app import search as search_mod  # noqa: E402
bl = search_mod.list_backlinks("projects/记忆.md")
check("反链命中 a.md", any(b["path"] == "a.md" for b in bl), bl)

# ── 会话 ──────────────────────────────────────────────────
from app import sessions as sess_mod  # noqa: E402
sess_mod.create_session("20250101-000000-test", "测试会话")
sess_mod.append_message("20250101-000000-test", "user", "你好")
sess_mod.append_message("20250101-000000-test", "assistant", "你好！")
r = c.get("/api/sessions", headers=H)
check("会话列表", r.status_code == 200 and len(r.json()) == 1)
msgs = sess_mod.load_messages("20250101-000000-test")
check("会话恢复", msgs == [{"role": "user", "content": "你好"},
                          {"role": "assistant", "content": "你好！"}], msgs)

# ── MCP 端点鉴权 + 初始化 ────────────────────────────────
r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18",
                                    "capabilities": {},
                                    "clientInfo": {"name": "smoke", "version": "0"}}})
check("MCP 无 token 401", r.status_code == 401, r.text)

r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-06-18",
                                    "capabilities": {},
                                    "clientInfo": {"name": "smoke", "version": "0"}}},
           headers={**H, "Accept": "application/json, text/event-stream"})
check("MCP initialize", r.status_code == 200, r.text[:300])

# ── Agent 工具执行（不走 LLM）────────────────────────────
from app import agent  # noqa: E402
res = agent._execute("write_file", {"path": "ai.md", "content": "hi"}, allow_write=False)
check("未授权写入被拒", isinstance(res, dict) and "未授权" in res.get("error", ""), res)
res = agent._execute("write_file", {"path": "ai.md", "content": "hi"}, allow_write=True)
check("授权后可写", res.get("path") == "ai.md", res)
res = agent._execute("delete_file", {"path": "ai.md"}, allow_write=True)
check("删除进回收站", res.get("trashed_to", "").startswith(".trash/"), res)

# ── 聊天（未配 LLM 时优雅报错）──────────────────────────
with c.stream("POST", "/api/chat", json={"message": "hi"}, headers=H) as r:
    body = "".join(r.iter_text())
check("chat 未配 LLM 报 error", '"type": "error"' in body and '"type": "done"' in body, body[:200])

c.__exit__(None, None, None)
print(f"\n全部通过（{ok} 项）")

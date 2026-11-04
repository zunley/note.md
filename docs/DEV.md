# 开发说明（实现备注）

面向开发/二次修改，使用说明见 [README.md](../README.md)。

## 目录结构

```
src/api/app/
├── main.py       # FastAPI 入口：REST + MCP 挂载 + 静态资源
├── config.py     # 环境变量配置
├── auth.py       # 口令登录、HMAC token、登录限速
├── filesvc.py    # 核心文件服务（REST/MCP 共用）：路径防护、CRUD、乐观锁、回收站
├── search.py     # 全文搜索 + 反链
├── sessions.py   # AI 会话记录 .agents/sessions/*.md
├── mcp_server.py # FastMCP tools（薄封装 filesvc/search/sessions）
├── agent.py      # LLM 工具调用循环 → SSE 事件流
└── models.py     # Pydantic 模型
src/web/src/
├── App.tsx        # 布局 / 状态 / 快捷键（⌘J AI，⌘N/⌘⇧N 新建）
├── api.ts         # REST + SSE 封装
├── Login.tsx      # 口令登录
├── FileTree.tsx   # 目录树、行内新建/重命名、右键菜单
├── Editor.tsx     # CodeMirror 6 + 自动保存 + 冲突处理
├── inlinePreview.ts # 内联预览（非光标行隐藏 markdown 标记）
├── Preview.tsx    # 分栏预览（markdown-it）
├── Chat.tsx       # assistant-ui 悬浮窗（LocalRuntime + 工具卡片 + 会话写授权）
└── theme.css      # 方案四 design tokens 与全部样式
```

## 本地开发

```bash
# 后端
python3 -m venv .venv && .venv/bin/pip install -r src/api/requirements.txt
NOTE_MD_ROOT=./notes NOTE_MD_PASSWORD=dev .venv/bin/python -m uvicorn app.main:app --app-dir src/api --port 8080

# 前端（vite dev server，代理 /api 与 /mcp 到 8080）
cd src/web && npm install && npm run dev     # http://localhost:5173

# 冒烟测试（27 项）
.venv/bin/python src/api/tests/smoke.py
```

## 常用命令（Makefile）

```bash
make dev       # 后端 uvicorn --reload + 前端 vite dev
make test      # 后端冒烟测试
make build     # 无缓存重建镜像
make deploy    # build + up
make release VERSION=0.1.0   # 打 v* tag 触发 CI 释出镜像
```

## 发布（CI）

`.github/workflows/release.yml`：推送 `v*` tag（或手动触发）→ 跑冒烟测试 + 前端构建 →
构建多架构镜像（linux/amd64 + linux/arm64）→ 推送 `ghcr.io/zunley/note.md:{x.y.z, x.y, latest}`。

## 实现与设计的偏差（对照 docs/PRODUCT.md）

| 项 | 状态 |
|----|------|
| F9 全文搜索 UI | API / MCP 已实现，前端搜索面板（⌘K）未做（P1） |
| F11 Markdown 内链补全 | 未做（P1） |
| 会话恢复 UI（/api/sessions → 悬浮窗） | 后端已实现，前端未接入 |
| 上传图片 | 按设计不做；预览渲染远程图片 |
| MCP 端点 | `/mcp`（streamable-http，Bearer token；`?token=` 兜底），无尾斜杠亦可 |
| 删除回收站 | `.trash/<时间戳>/<原路径>`，无清理 UI（手动清理） |
| 会话记录 | `.agents/sessions/<id>.md`，含工具调用摘要 |

## 要点备忘

- token 为自实现 HMAC-SHA256 签名（`v1.<payload>.<sig>`），无 PyJWT 依赖；
- 保存乐观锁：`PUT /api/files/content` 带 `base_hash`，不匹配返回 409，前端出冲突横幅（重新加载/覆盖保存）；
- MCP 子应用 lifespan 已接入 FastAPI lifespan（fastmcp 4.x `http_app(path="/")` + `AsyncExitStack`）；
- `Mount("/mcp")` 不匹配裸路径，另用 `app.add_route("/mcp", ...)` 兜底并归一化 path；
- 内联预览基于**语法树 token** 隐藏标记（HeaderMark/EmphasisMark/LinkMark/CodeMark/StrikethroughMark/URL…，需在 markdown() 启用 Strikethrough/TaskList/Autolink 扩展），光标行标记保持可见；
- **`.cm-line` 禁止 margin**（margin 折叠破坏 CM6 行高测量 → 光标垂直移动跳顶、视觉错乱），行间距只用 padding；
- 编辑器/预览为**内部滚动**（cm-scroller / preview-pane 各自滚动，页面不滚）；分栏时两侧按滚动比例同步，用「自发滚动识别」（比对上次同步写入值）防回环，不丢帧；
- UI 真实浏览器验证：`node src/web/tests/ui-check.mjs`（复用 files.md 的 playwright；需先起 :8088 服务，见脚本头注释；含 ArrowUp/标记隐藏/预览样式/同步滚动断言与截图）；`window.__cm` 为测试钩子；
- 目录树默认全折叠，打开文件自动展开祖先链；新建由输入结尾决定类型（`名字/`=目录、`名字.md`=文件），无常驻新建按钮；
- 字体经 fontsource 全量打包（unicode-range 分片按需加载），构建产物约 5MB 字体文件，首屏只加载命中分片。

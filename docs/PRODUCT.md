# note.md — Web Markdown 笔记本 · 产品定义（v1.0 定稿）

> 状态：**已定稿**（2025-11）。样式已定稿（§6），实现状态见文末附注。
> 定位一句话：**运行在容器里的、AI 原生的个人 Markdown 笔记本**——
> 挂载一个目录即拥有全部数据，浏览器里即时读写，AI 助手直接帮你管理文件与查找内容。

---

## 1. 背景与定位

### 1.1 是什么
一个自托管（self-hosted）的 Web 笔记应用：

- 数据即文件：笔记本根目录是一个普通目录，全部为纯 Markdown，挂载进容器即可用；
- 界面克制：**现代纸感**——干净、明亮、留白充分（files.md 只借鉴其「纸面 + 少量点缀色」的色彩关系，视觉基调重新设计）；
- AI 原生：内置悬浮窗对话面板（assistant-ui），后端通过 **FastMCP** 暴露文件管理/检索工具，
  AI 可以真正「动手」——建文件、改内容、全文查找、整理目录，而不是只能聊天。

### 1.2 目标用户
单人 / 家庭内网使用（homelab 部署，可经 Cloudflare / frp 暴露）。**单用户假设**，不做多租户。

### 1.3 设计原则
1. **文件即真相**（file-first）：不引入数据库存正文；目录结构可被 git、同步盘、其他工具直接消费。
2. **低认知负担**：功能克制，一个屏幕装下全部操作；代码库保持一个人（或一个 LLM）能读懂。
3. **AI 是一等公民**：AI 能力不是外挂聊天窗，而是与 REST 共用同一套文件服务语义（MCP tools ≈ REST 的能力镜像）。
4. **容器即交付**：单镜像、单卷挂载、少量环境变量，compose 一行起服务。

### 1.4 非目标（明确不做）
- 多用户 / 权限体系 / 协同编辑 / OT-CRDT
- 版本历史（交给挂载目录上的 git/备份，`workflow/backup.sh` 已覆盖）
- 移动端原生 App（Web 响应式即可）
- 图片上传与媒体库管理（预览中仅**渲染** Markdown 图片语法，不提供上传/管理）
- 深色模式、拖拽排序、⌘P 快速跳转、PWA 离线、Mermaid/KaTeX 渲染（原 P2 项，全部暂不规划）
- 富文本 block 编辑器（Notion 类）
- 端到端加密

---

## 2. 核心功能范围

### P0（MVP 必须）
| # | 功能 | 说明 |
|---|------|------|
| F1 | 目录树浏览 | 左侧栏树形展示；展开/折叠、当前文件高亮、新建/重命名/删除入口 |
| F2 | 文件打开与编辑 | 打开 .md 进入编辑器；自动保存（防抖）+ 手动保存；脏状态提示 |
| F3 | 新建文件 / 文件夹 | **树内行内输入**创建，目标目录明确可见（规则见 §3）；侧栏单入口 + 快捷键（⌘N / ⌘⇧N） |
| F4 | 即时编写预览 | 编辑即所见：**内联渲染（方案 A）为主，分栏预览（方案 B）可切换** |
| F5 | 登录口令 → token | 单口令登录，换取带过期时间的 token；所有 API 与 MCP 均校验 |
| F6 | AI 悬浮窗对话 | assistant-ui 聊天；**悬浮按钮 + 快捷键开合**（非固定侧栏）；流式输出，可调用 MCP 文件工具 |
| F7 | MCP Server | FastMCP 提供文件读写/查找工具，既服务内置聊天，也可被外部 MCP 客户端接入 |
| F8 | 容器化部署 | Dockerfile + compose；挂载 `/notes` 为笔记本根目录；容器默认端口 **8080** |

### P1（MVP 后紧跟）
| # | 功能 | 说明 |
|---|------|------|
| F9 | 全文搜索 | 标题 + 正文关键词搜索，结果跳转到文件 |
| F10 | 写入冲突保护 | 保存带内容哈希乐观锁，外部改动（AI/同步盘）不被静默覆盖 |
| F11 | Markdown 内链 | `[x](path.md)` 文件名自动补全，点击跳转 |
| F12 | AI 工具会话级授权 | 写类工具按**会话**放开（见 §5.3） |

> 文件可见性规则：文件树**只显示 `.md` 文件**；其他文件与隐藏目录（含 `.agents/`）一律不显示。

---

## 3. 交互与信息架构

```
┌────────────────────────────────────────────────────────────┐
│  note.md                       [搜索 ⌘K]        [···] [锁]  │ 顶栏（极简）
├───────────┬────────────────────────────────────────────────┤
│ ▾ journal │                                                │
│ ▾ brain   │              编辑器 / 即时预览区                 │
│   记忆.md │                                                │
│   偏差.md │        正文列最大宽度 ~800px 居中                │
│ ▾ projects│        现代纸感：纸底 + 硬边 + 偏移阴影            │
│ [＋ 新建]  │                                                │
└───────────┴────────────────────────────────────────────────┘
                                         （右下角悬浮 AI 按钮 ✦）
              ┌──────────────────────┐
              │  AI 助手（悬浮面板）   │   点击 ✦ 或快捷键开合
              │  对话 / 工具卡片 / 输入 │   可拖宽、可全屏
              └──────────────────────┘
```

- **双栏 + 悬浮窗**：左侧文件树可折叠；AI 助手是**悬浮面板**（点击右下角 ✦ 按钮或快捷键（⌘J，⏳ 可配）开合），打开时浮在编辑区上方，可调宽/全屏，关闭后编辑区完整。
- **编辑体验**（F4）：
  - 模式 A（默认）：源码内联渲染——边写边见样式，光标处展开 Markdown 源码语法；
  - 模式 B：左右分栏（左源码右预览），顶栏一键切换；
- **保存策略**：停止输入 800ms 自动保存；顶部显示 `已保存 / 保存中 / 保存失败` 状态；离开页面前脏检查。
- **新建交互**（F3）：新建一律以**树内行内输入**呈现——输入框在目标目录下方展开，前缀显示目标目录（如 `brain/`），Esc 取消。**类型由输入结尾决定：以 `/` 结尾 = 新建文件夹；以 `.md` 结尾 = 新建文件；其余结尾拒绝提交并提示**（支持 `a/b/`、`a/b.md` 嵌套路径）。目标目录按优先级解析：
  1. 目录行悬停出现的 `＋` 按钮 / 右键「新建」所指定的目录；
  2. 否则：当前打开文件所在目录；
  3. 否则：根目录。
  目录树**默认全部折叠**（打开文件时自动展开其祖先链）；侧栏不设常驻新建按钮，⌘N / ⌘⇧N 为同一新建入口的快捷键。
- **文件树**：只显示 `.md`；点击即打开；右键菜单：新建 / 重命名 / 删除（进回收站）；目录行悬停出 `＋`（新建到该目录）。
- **目录约定**：不强加任何约定目录——不引入 files.md 的 `Chat.md` / `journal/` 等结构，笔记本布局完全由用户自定义；应用仅管理两个隐藏目录（`.trash/`、`.agents/`）。

---

## 4. AI 能力设计（FastMCP + assistant-ui）

### 4.1 总体架构
```
assistant-ui (悬浮聊天窗)
     │  SSE / POST /api/chat（Bearer token）
     ▼
FastAPI 网关 ──┬── REST API（编辑器用）
               ├── Agent 运行时（LLM 编排，后端持有 key）
               └── FastMCP server（同一进程内挂载，/mcp）
                        │
                        ▼
                  文件服务层 filesvc（REST 与 MCP 共用）
                        │
                        ▼
                  /notes 挂载目录
```

关键点：**MCP tools 与 REST API 调用同一个文件服务层**，权限、路径校验、冲突保护只写一份。
MCP 端点（streamable-http）同时供两个消费者：
1. 内置聊天的 Agent（进程内直调 tools，不经网络）；
2. 外部 MCP 客户端（Cursor / Claude Desktop / pi 等，经 `http(s)://host/mcp` + token 接入）。

**LLM key 只存在于后端**（环境变量），前端永不持有；聊天经 `/api/chat` SSE 由后端代理。

### 4.2 MCP Tools 规划

| Tool | 类型 | 参数 | 语义 |
|------|------|------|------|
| `list_tree` | 读 | `path?, depth?` | 列出目录树（名称/大小/修改时间） |
| `read_file` | 读 | `path, offset?, limit?` | 读文件内容（大文件分段） |
| `search_files` | 读 | `query, glob?, regex?` | 全文检索，返回 文件:行号 + 上下文片段 |
| `list_backlinks` | 读 | `path` | 谁引用了这个笔记（反链） |
| `get_outline` | 读 | `path` | 提取标题大纲（内容提取/摘要辅助） |
| `create_file` | 写 | `path, content?` | 新建（已存在则报错） |
| `write_file` | 写 | `path, content, base_hash?` | 覆盖写入（乐观锁可选） |
| `append_file` | 写 | `path, content` | 追加（速记/日志场景） |
| `move_file` | 写 | `from, to` | 移动/重命名 |
| `delete_file` | 写 | `path` | 删除（**统一移入 `.trash/` 回收站**） |

- 所有 `path` 均相对笔记本根目录，服务端做路径穿越防护（resolve 后必须仍在根内）；
- 工具只管理 `.md`；隐藏目录 `.agents/` 对 AI 可读（作为会话记忆），但不可由 AI 创建/修改其中内容（会话记录由后端写入）。

### 4.3 内置聊天（assistant-ui 悬浮窗）
- 组件：`@assistant-ui/react`，主题按 §6 定制为现代纸感；
- 悬浮形态：右下角 FAB（✦）开合，快捷键（⌘J）全局呼出/收起；面板可拖宽、可全屏；
- 流式输出（SSE），工具调用渲染为可折叠卡片：
  - 读工具：显示「查看了 brain/记忆.md」；
  - 写工具：显示变更摘要 / diff，按 §5.3 的会话级授权决定是否直接执行；
- **会话持久化**：按 session 存为 Markdown——`<notebook>/.agents/sessions/*.md`
  （一个会话一个文件，含时间戳、用户消息、AI 回复与工具调用摘要；文件树不显示）；
- 提示词约束：要求 AI 先 `search_files` / `read_file` 再改动；回答中的文件路径可点击跳转到编辑器。

---

## 5. 权限与认证

### 5.1 模型
**单口令 → 动态 token**，无用户表、无注册：

1. 部署时以环境变量提供登录口令（`NOTE_MD_PASSWORD`，建议只存哈希 `NOTE_MD_PASSWORD_HASH`）；
2. `POST /api/auth/login` 校验口令，签发 **JWT（HS256）**，含 `exp`；
3. 之后所有请求携带 `Authorization: Bearer <token>`；
4. token 过期后回登录页重新换取；支持 `POST /api/auth/refresh` 在有效期内滚动续期。

**TTL 可配**：`NOTE_MD_TOKEN_TTL`（如 `24h` / `72h` / `30d`），默认 `72h`。无吊销列表——更换口令即全部失效。

### 5.2 校验范围
| 入口 | 校验方式 |
|------|----------|
| REST API | `Authorization: Bearer` |
| MCP `/mcp` | 同上（外部 MCP 客户端配置 header）；SSE 长连接允许 `?token=` 兜底 |
| 前端静态资源 | 不校验（登录页本身）；API 全部受保护 |
| LLM Key | 仅存服务端环境变量，**绝不下发前端** |

### 5.3 写操作授权（AI 侧）
- 读类工具：直接执行；
- 写类工具：**按会话放开**——会话内首次写操作时弹出一次性确认（「本会话允许 AI 修改文件？」），同意后本会话内写操作直接执行；新会话重新询问；
- 删除永远移入 `.trash/` 回收站，不做物理删除；
- 环境变量 `NOTE_MD_AI_AUTO_WRITE=1` 可全局免确认（信任场景）。

### 5.4 其他安全
- 口令登录限速（同 IP 5 次/分钟，防爆破）；
- 保存/写入统一路径白名单校验；过滤 `..`、绝对路径、控制字符；
- 容器内以非 root 用户运行，`/notes` 挂载 rw，其余只读。

---

## 6. 视觉风格与字体

### 6.1 风格基调：现代纸感（Modern Paper）—— 定稿「方案四 · 轻新粗野」
- **定稿**：`docs/style/mockup-4-neo-clean.html`。files.md 只取其「纸底 + 少量高饱和点缀 + 文字为主角」的色彩关系，
  视觉语言现代化：**纸白底 + 2px 纯色硬边 + 偏移硬阴影（无高斯模糊）+ 粗黑标题 + 大圆角**，干净、明快、不陈旧。

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg` | `#FAF8F2` | 页面纸底 |
| `--panel` | `#F2EFE6` | 侧栏 / 面板 / 引用块底 |
| `--card` | `#FFFDF7` | 编辑纸面 / 卡片 / 输入框 |
| `--tx` | `#1A1A1A` | 正文 / 边框 |
| `--tx-2` | `#7A776C` | 次要文字 |
| `--tx-3` | `#B2AE9F` | 弱化文字（meta） |
| `--line` | `#DAD5C4` | 分隔线 |
| `--blue` | `#2E5CFF` | 链接 / 选中项 / 主按钮 |
| `--orange` | `#E8912D` | 标题装饰点 / 工具卡片标记 |
| `--lime` | `#DCF277` | 行内代码 chip / 状态徽章 / hover |

- 样式语言：卡片/按钮 `border: 2px solid var(--tx)` + `box-shadow: 4~8px 4~8px 0`（纯偏移、无模糊）；圆角 8–16px；hover 微位移加深阴影；代码块深底（`#23221E`）反白；引用块柠檬色偏移阴影。
- 标题：中文 Noto Sans SC 900，`letter-spacing: -0.01em`；h2 前置橙色小方块装饰。
- 暗色模式不做（P2 已裁撤）。

### 6.2 字体（自托管 webfont，服务端默认嵌入）
- **决策**：不依赖用户系统字体，webfont 下载到项目内，由服务端静态托管（`/fonts`），默认启用；
- 组合（已定稿）：
  - 拉丁/数字：**Space Grotesk**（500/600/700）；
  - 中文正文：**Noto Sans SC**（400/500；fontsource 的 unicode-range 分片 woff2，按需加载）；
  - 中文标题：**Noto Sans SC 900**（粗黑大字）；
  - 代码/行内代码：**JetBrains Mono**（400/500，拉丁）+ Noto Sans SC 回退；
- 中文排版参数：正文 `line-height: 1.75~1.9`，段距大于行距；标题加粗、字距微收；
- 体积控制：只打包用到的字重（通常 3–4 个 woff2 分片组合），首屏 < 500KB。

---

## 7. 接口规划（HTTP + 函数级）

### 7.1 REST API（FastAPI，前缀 `/api`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/auth/login` | `{password}` → `{token, expires_at}` |
| `POST` | `/auth/refresh` | 续期 token |
| `GET` | `/files/tree` | `?path=&depth=` 返回目录树 JSON（仅 .md） |
| `GET` | `/files/content` | `?path=` → `{content, hash, mtime, size}` |
| `PUT` | `/files/content` | `{path, content, base_hash?}` 保存（hash 不匹配 → 409） |
| `POST` | `/files` | `{path, type: file\|dir, content?}` 新建 |
| `POST` | `/files/move` | `{from, to}` 重命名/移动 |
| `DELETE` | `/files` | `?path=` 删除（进 `.trash/`） |
| `GET` | `/search` | `?q=&glob=` 全文搜索 |
| `GET` | `/sessions` | 会话列表（读 `.agents/sessions/`） |
| `GET` | `/sessions/{id}` | 会话内容（历史对话恢复到悬浮窗） |
| `POST` | `/chat` | 聊天消息 → SSE 流（token / tool_call / tool_result / done 事件） |
| `GET` | `/health` | 存活探针（免鉴权） |

> 无 `/raw/*`（不做图片资源服务）；Markdown 图片语法仅渲染远程 URL。

### 7.2 服务端模块 / 函数规划

```
src/api/
├── main.py            # FastAPI app + 静态资源/字体托管 + MCP 挂载
├── config.py          # env 加载：密码、token TTL、LLM 配置、根目录、auto_write
├── auth.py            # issue_token() verify_token() login_limiter()
├── filesvc.py         # 核心文件服务（REST 与 MCP 共用）
│   ├── resolve_path(rel) -> Path          # 路径穿越防护
│   ├── get_tree(path, depth) -> TreeNode  # 仅 .md，隐藏 .agents/ 等
│   ├── read_file(path, offset, limit) -> FileContent
│   ├── write_file(path, content, base_hash) # 乐观锁
│   ├── create(path, kind) / move(src, dst)
│   ├── trash(path)                        # 移入 .trash/
│   └── compute_hash(content) -> str
├── search.py          # search(query, glob, regex) -> list[Hit]
│                      # v1 自实现遍历（目录规模小），后续可换 sqlite fts5
├── mcp_server.py      # FastMCP 实例 + §4.2 十个 tool（薄封装 filesvc）
├── agent.py           # LLM 运行时：build_llm() / run_chat(session) -> AsyncIterator[Event]
│                      # 进程内注册 mcp tools；会话写入 .agents/sessions/*.md
├── sessions.py        # session 文件读写：list_sessions() load() append_event()
└── models.py          # Pydantic：TreeNode / FileContent / Hit / ChatEvent / SessionMeta
```

### 7.3 前端模块规划

```
src/web/
├── App.tsx            # 双栏布局 + 悬浮 AI 面板 / 路由状态
├── auth/              # LoginGate, useToken()（localStorage + 过期管理）
├── tree/              # FileTree, TreeNode, useTree()（缓存 + 变更后失效）
├── editor/            # Editor.tsx（CodeMirror 6）, useAutoSave(), Preview.tsx（分栏模式）
├── chat/              # AssistantFloat.tsx（FAB + 悬浮面板）, ToolCard, SessionGate
├── api/               # fetch 封装（自动附 token、401 跳登录）
└── styles/            # theme.css（§6 tokens）, fonts.css
```

---

## 8. 技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 后端 | Python 3.12 + **FastAPI** + **FastMCP** | FastMCP 与 FastAPI 同进程挂载（`mcp.streamable_http_app()`），一份文件服务双出口 |
| Agent/LLM | OpenAI 兼容接口（`OPENAI_BASE_URL/KEY/MODEL`），后端代理 | key 不出服务端；对接自建 LLM 网关 |
| 前端 | **React + Vite + TypeScript** | assistant-ui 为 React 生态 |
| 编辑器 | **CodeMirror 6** | 轻量、markdown 模式成熟、易做内联渲染 |
| 聊天 UI | **@assistant-ui/react** | 需求指定；主题可定制 |
| 字体 | fontsource 分片 woff2 自托管 | 中文体积可控，默认嵌入 |
| 打包 | 多阶段 Dockerfile：前端 build → 后端单镜像（uvicorn） | 一个容器跑全部 |
| 部署 | compose：`8080:8080` + `./notes:/notes` + env | 应用只关心自身默认端口 8080，对外映射由部署方决定 |

---

## 9. 部署形态

```yaml
services:
  note-md:
    image: note-md:latest
    ports: ["8080:8080"]
    volumes:
      - ./notes:/notes            # 笔记本根目录（唯一必须挂载）
    environment:
      NOTE_MD_PASSWORD: ${NOTE_MD_PASSWORD}
      NOTE_MD_TOKEN_TTL: 72h      # 可配：24h / 72h / 30d ...
      OPENAI_BASE_URL: https://llm-gateway/...
      OPENAI_API_KEY: ${LLM_KEY}
      OPENAI_MODEL: qwen-plus
      TZ: Asia/Shanghai
    restart: unless-stopped
```

- 挂载目录语义：**根目录即笔记本**，无 schema、无初始化脚本；空目录启动时给引导页（可一键生成示例结构）；
- 目录内约定：`.trash/`（回收站）、`.agents/sessions/`（AI 会话记录）由应用管理，文件树不显示；
- 备份：直接复用 `workflow/backup.sh` 对 `notes/` 目录备份；
- 时区在镜像内预置，保证日期与排序正确。

---

## 10. 决议记录

| # | 问题 | 决议 |
|---|------|------|
| Q1 | 搜索范围 | 全文搜索放 P1，MVP 先保证读写与 AI |
| Q2 | 编辑器形态 | A+B，A（内联）为主，B（分栏）可切换 |
| Q3 | 中文字体 | 自托管 webfont，服务端默认嵌入（Noto Sans SC 等，以样式选型为准） |
| Q4 | LLM 走向 | 后端持有 key，`/api/chat` SSE 代理 |
| Q5 | AI 写确认 | **按会话放开**（首次一次性确认，会话内免确认；删除永远进回收站） |
| Q6 | 删除语义 | 统一进 `.trash/` 回收站 |
| Q7 | 聊天记录 | 按 session 存 `.agents/sessions/*.md` |
| Q8 | 端口 | 应用只关心默认端口 8080 |
| Q9 | token TTL | 可配（`NOTE_MD_TOKEN_TTL`），默认 72h |
| Q10 | 文件范围 | 只管理/显示 `.md`，其他文件不显示 |
| Q11 | 样式定稿 | **方案四「轻新粗野」**，tokens 见 §6.1 |
| Q12 | 新建层级 | 树内行内输入 + 目标目录解析规则（§3）；类型由输入结尾决定（`名字/`/`名字.md`），无常驻新建按钮 |
| Q13 | 约定目录 | 不引入 Chat.md / journal/ 等 files.md 约定，目录结构完全用户自定义 |

**遗留小项**（编码前顺手定）：
- AI 悬浮窗快捷键（暂定 ⌘J）；
- `.trash/` 清理策略（暂不提供 UI，手动清理）。

---

## 11. 里程碑

1. **M1 骨架**：容器 + 挂载目录 + 登录 token + 目录树 + 打开/编辑/保存 + 新建文件（只 .md）；
2. **M2 写作体验**：内联预览 + 分栏切换、自动保存、冲突保护、webfont 与主题定稿落地；
3. **M3 AI 原生**：FastMCP tools + assistant-ui 悬浮窗 + 会话级授权 + 会话记录落盘；
4. **M4 打磨**：全文搜索、内链补全、`.trash/` 与会话的轻量管理 UI。

> **实现状态（2025-11）**：M1–M3 已完成并通过冒烟测试（27 项）与 Docker 端到端验证；
> M4 部分完成（搜索与反链已实现于 API/MCP 层，前端 ⌘K 搜索面板、内链补全、会话恢复 UI 未做）。
> 偏差明细与开发说明见 [docs/DEV.md](DEV.md)。

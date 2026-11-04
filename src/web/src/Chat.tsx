/**
 * AI 悬浮窗：assistant-ui LocalRuntime + /api/chat SSE。
 * 工具卡片按「读/写」着色；写操作按会话授权（write-gate 复选框）。
 */
import { useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  type ChatModelAdapter,
} from "@assistant-ui/react";

import { chatEvents } from "./api";
import { md } from "./markdown";

/** App 注入的全局动作（工具卡片点击打开文件）。 */
export const chatActions = {
  openFile: (_path: string) => {},
};

const WRITE_TOOLS = new Set([
  "create_file",
  "write_file",
  "append_file",
  "move_file",
  "delete_file",
]);

// ── 消息部件渲染 ─────────────────────────────────────────
const MarkdownPart = (props: { text: string }) => (
  <div dangerouslySetInnerHTML={{ __html: md.render(props.text) }} />
);

const ToolCard = (props: any) => {
  const result = props.result as { summary?: string; error?: string | null } | undefined;
  const write = WRITE_TOOLS.has(props.toolName);
  const summary =
    result?.summary ??
    `${props.toolName}(${JSON.stringify(props.args ?? {}).slice(0, 60)})`;
  const path = (props.args as Record<string, unknown>)?.path as string | undefined;
  return (
    <div
      className={`tool-card${write ? " write" : ""}${props.isError ? " err" : ""}`}
      title={summary}
    >
      <span className="tag">{write ? "写" : "读"}</span>
      <span className="summary">{summary}</span>
      {path && (
        <button className="link" onClick={() => chatActions.openFile(path)}>
          打开
        </button>
      )}
    </div>
  );
};

const UserMessage = () => (
  <MessagePrimitive.Root className="msg-user">
    <MessagePrimitive.Parts components={{ Text: MarkdownPart } as any} />
  </MessagePrimitive.Root>
);

const AssistantMessage = () => (
  <MessagePrimitive.Root className="msg-ai">
    <MessagePrimitive.Parts
      components={
        {
          Text: MarkdownPart,
          tools: { Fallback: ToolCard },
        } as any
      }
    />
  </MessagePrimitive.Root>
);

// ── 面板 ─────────────────────────────────────────────────
export function Chat({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [allowWrite, setAllowWrite] = useState(false);
  const [wide, setWide] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const allowWriteRef = useRef(false);
  allowWriteRef.current = allowWrite;

  const adapter = useMemo<ChatModelAdapter>(
    () => ({
      async *run({ messages, abortSignal }) {
        const last = [...messages].reverse().find((m) => m.role === "user");
        const text = (last?.content ?? [])
          .map((p: any) => (p.type === "text" ? p.text : ""))
          .join("\n");
        const content: any[] = [];
        const toolIdx = new Map<string, number>();
        let errMsg: string | null = null;
        try {
          for await (const ev of chatEvents(
            text,
            sessionIdRef.current,
            allowWriteRef.current,
            abortSignal,
          )) {
            switch (ev.type) {
              case "session":
                sessionIdRef.current = ev.id as string;
                break;
              case "token": {
                const p = content[content.length - 1];
                if (p?.type === "text") p.text += ev.text;
                else content.push({ type: "text", text: ev.text });
                break;
              }
              case "tool_call":
                toolIdx.set(ev.id as string, content.length);
                content.push({
                  type: "tool-call",
                  toolCallId: ev.id,
                  toolName: ev.name,
                  args: (ev.args as object) ?? {},
                  argsText: JSON.stringify(ev.args ?? {}),
                });
                break;
              case "tool_result": {
                const i = toolIdx.get(ev.id as string);
                if (i !== undefined) {
                  content[i].result = { summary: ev.summary, error: ev.error ?? null };
                  content[i].isError = !ev.ok;
                }
                break;
              }
              case "error":
                errMsg = ev.message as string;
                break;
            }
            yield { content: content.map((p) => ({ ...p })), status: { type: "running" } };
          }
        } catch (e: any) {
          if (e?.name !== "AbortError") errMsg = String(e?.message ?? e);
        }
        if (errMsg) content.push({ type: "text", text: `\n\n⚠️ ${errMsg}` });
        yield {
          content,
          status: errMsg
            ? ({ type: "incomplete", reason: "error", error: errMsg } as const)
            : ({ type: "complete", reason: "stop" } as const),
        };
      },
    }),
    [],
  );

  const runtime = useLocalRuntime(adapter);

  if (!open) return null;

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={`ai-panel${wide ? " wide" : ""}`}>
        <div className="ai-head">
          ✦ AI 助手
          <button
            className="x"
            style={{ marginLeft: "auto", marginRight: 4 }}
            onClick={() => setWide((v) => !v)}
            title={wide ? "收窄" : "加宽"}
          >
            {wide ? "◧" : "◨"}
          </button>
          <button className="x" onClick={onClose} title="关闭 (⌘J)">
            ×
          </button>
        </div>
        <div className="write-gate">
          <label>
            <input
              type="checkbox"
              checked={allowWrite}
              onChange={(e) => setAllowWrite(e.target.checked)}
            />
            允许 AI 修改本会话文件
          </label>
          {allowWrite ? (
            <span className="badge">已授权写入</span>
          ) : (
            <span className="badge off">只读</span>
          )}
        </div>
        <ThreadPrimitive.Root className="aui-thread">
          <ThreadPrimitive.Empty>
            <div className="aui-empty">
              让 AI 帮你管理笔记：
              <br />
              「找一下所有提到部署的笔记」
              <br />
              「把 projects 下的文件整理出一个索引」
            </div>
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
        </ThreadPrimitive.Root>
        <ComposerPrimitive.Root className="ai-composer">
          <ComposerPrimitive.Input
            placeholder="让 AI 帮你管理笔记…（⌘J 开关）"
            rows={1}
          />
          <ThreadPrimitive.If running={false}>
            <ComposerPrimitive.Send>发送</ComposerPrimitive.Send>
          </ThreadPrimitive.If>
          <ThreadPrimitive.If running>
            <ComposerPrimitive.Cancel>停止</ComposerPrimitive.Cancel>
          </ThreadPrimitive.If>
        </ComposerPrimitive.Root>
      </div>
    </AssistantRuntimeProvider>
  );
}

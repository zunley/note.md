/** REST API 封装 + token 管理 + SSE 聊天流。 */

export interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  mtime: number;
  size: number;
  children?: TreeNode[] | null;
}

export interface FileContent {
  path: string;
  content: string;
  hash: string;
  mtime: number;
  size: number;
}

const KEY = "note-md.auth";

export interface Auth {
  token: string;
  exp: number;
}

export function loadAuth(): Auth | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const a = JSON.parse(raw) as Auth;
    return a.exp * 1000 > Date.now() ? a : null;
  } catch {
    return null;
  }
}

export function saveAuth(a: Auth) {
  localStorage.setItem(KEY, JSON.stringify(a));
}

export function clearAuth() {
  localStorage.removeItem(KEY);
}

function headers(): Record<string, string> {
  const a = loadAuth();
  return {
    "Content-Type": "application/json",
    ...(a ? { Authorization: `Bearer ${a.token}` } : {}),
  };
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    clearAuth();
    location.reload();
  }
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (password: string) =>
    req<Auth & { expires_at: number }>("POST", "/api/auth/login", { password }),
  tree: () => req<TreeNode>("GET", "/api/files/tree"),
  read: (path: string) =>
    req<FileContent>("GET", `/api/files/content?path=${encodeURIComponent(path)}`),
  write: (path: string, content: string, baseHash?: string) =>
    req<FileContent>("PUT", "/api/files/content", {
      path,
      content,
      base_hash: baseHash ?? null,
    }),
  create: (path: string, type: "file" | "dir" = "file", content = "") =>
    req<TreeNode>("POST", "/api/files", { path, type, content }),
  move: (src: string, dst: string) =>
    req<TreeNode>("POST", "/api/files/move", { src, dst }),
  remove: (path: string) =>
    req<{ trashed_to: string }>("DELETE", `/api/files?path=${encodeURIComponent(path)}`),
};

// ── SSE 聊天 ─────────────────────────────────────────────
export interface ChatEvent {
  type: "session" | "token" | "tool_call" | "tool_result" | "error" | "done";
  [k: string]: unknown;
}

export async function* chatEvents(
  message: string,
  sessionId: string | null,
  allowWrite: boolean,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      message,
      session_id: sessionId,
      allow_write: allowWrite,
    }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`聊天请求失败 (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data:")) {
          yield JSON.parse(line.slice(5).trim()) as ChatEvent;
        }
      }
    }
  }
}

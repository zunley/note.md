import { useCallback, useEffect, useState } from "react";
import { api, clearAuth, loadAuth, type FileContent, type TreeNode } from "./api";
import { Login } from "./Login";
import { FileTree, type NewTarget } from "./FileTree";
import { Editor, STATUS_TEXT, type SaveStatus } from "./Editor";
import { Chat, chatActions } from "./Chat";

export default function App() {
  const [authed, setAuthed] = useState(() => !!loadAuth());
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [file, setFile] = useState<FileContent | null>(null);
  const [mode, setMode] = useState<"inline" | "split">("inline");
  const [chatOpen, setChatOpen] = useState(false);
  const [newTarget, setNewTarget] = useState<NewTarget | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");

  const refresh = useCallback(async () => {
    try {
      setTree(await api.tree());
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (authed) void refresh();
  }, [authed, refresh]);

  const open = useCallback(async (path: string) => {
    try {
      setFile(await api.read(path));
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    chatActions.openFile = (p) => void open(p);
  }, [open]);

  // 快捷键：⌘J 开关 AI，⌘N / ⌘⇧N 新建（类型由输入结尾决定）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const k = e.key.toLowerCase();
      if (k === "j") {
        e.preventDefault();
        setChatOpen((v) => !v);
      } else if (k === "n") {
        e.preventDefault();
        setNewTarget({ dir: activeDirOf(file) });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  if (!authed) return <Login onDone={() => setAuthed(true)} />;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          note<em>.</em>md
        </div>
        {file && (
          <div className="path">
            <b>{file.path}</b>
          </div>
        )}
        {file && (
          <div
            className={`save-status${
              saveStatus === "error" || saveStatus === "conflict"
                ? " err"
                : saveStatus === "saving"
                  ? " saving"
                  : ""
            }`}
          >
            {saveStatus === "saved" ? "✓ 已保存" : STATUS_TEXT[saveStatus]}
          </div>
        )}
        <div className="spacer" />
        <button
          className="nb-btn"
          onClick={() => setMode((m) => (m === "inline" ? "split" : "inline"))}
          title="切换 编辑模式 / 分栏预览"
        >
          {mode === "inline" ? "分栏预览" : "内联模式"}
        </button>
        <button className="nb-btn" onClick={logout}>
          退出
        </button>
      </header>

      <div className="layout">
        <aside className="sidebar">
          {tree ? (
            <FileTree
              root={tree}
              activePath={file?.path ?? null}
              newTarget={newTarget}
              onOpen={(p) => void open(p)}
              onChanged={() => void refresh()}
              onNewConsumed={() => setNewTarget(null)}
            />
          ) : (
            <div style={{ padding: 20, color: "var(--tx-3)", fontSize: "0.85rem" }}>
              加载中…
            </div>
          )}
        </aside>

        {file ? (
          <Editor
            file={file}
            mode={mode}
            onSaved={(f) =>
              setFile((prev) =>
                prev ? { ...prev, hash: f.hash, mtime: f.mtime, size: f.size } : prev,
              )
            }
            onStatusChange={setSaveStatus}
          />
        ) : (
          <div className="editor-wrap">
            <div className="empty-state">
              <h2>开始写作</h2>
              <p>
                左侧是你的笔记本，全部为纯 .md 文件。
                <br />
                目录行的 ＋ 号新建：<b>名字.md</b> 建文件，<b>名字/</b> 建目录。
              </p>
              <button
                className="nb-btn solid"
                onClick={() => setNewTarget({ dir: "" })}
              >
                ＋ 新建
              </button>
            </div>
          </div>
        )}
      </div>

      {!chatOpen && (
        <button className="fab" title="AI 助手 (⌘J)" onClick={() => setChatOpen(true)}>
          ✦
        </button>
      )}
      <Chat open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );

  function logout() {
    clearAuth();
    setAuthed(false);
    setFile(null);
    setTree(null);
    setChatOpen(false);
    setSaveStatus("saved");
  }
}

function activeDirOf(file: FileContent | null): string {
  if (!file) return "";
  const i = file.path.lastIndexOf("/");
  return i < 0 ? "" : file.path.slice(0, i);
}

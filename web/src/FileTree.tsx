import { useEffect, useRef, useState } from "react";
import { api, type TreeNode } from "./api";

export interface NewTarget {
  dir: string; // 目标目录（相对路径，"" 为根）；类型由输入结尾决定
}

interface Props {
  root: TreeNode;
  activePath: string | null;
  newTarget: NewTarget | null;
  onOpen: (path: string) => void;
  onChanged: () => void;
  onNewConsumed: () => void;
}

interface Menu {
  x: number;
  y: number;
  node: TreeNode;
}

function parentOf(path: string): string {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}

function join(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name;
}

/** 展开 dir 的整条祖先链。 */
function chainOf(dir: string): string[] {
  if (!dir) return [];
  const parts = dir.split("/");
  return parts.map((_, i) => parts.slice(0, i + 1).join("/"));
}

export function FileTree({
  root,
  activePath,
  newTarget,
  onOpen,
  onChanged,
  onNewConsumed,
}: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [menu, setMenu] = useState<Menu | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [localTarget, setLocalTarget] = useState<NewTarget | null>(null);
  const [inputErr, setInputErr] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // 侧栏/快捷键触发的 newTarget 优先；目录行 ＋ 按钮设置 localTarget
  const target = newTarget ?? localTarget;

  const expandChain = (dir: string) =>
    setExpanded((s) => new Set([...s, ...chainOf(dir)]));

  // 打开文件时自动展开其祖先链
  useEffect(() => {
    if (activePath) expandChain(parentOf(activePath));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePath]);

  // 出现新建输入行时：展开目标目录链 + 聚焦
  useEffect(() => {
    if (target) {
      expandChain(target.dir);
      setInputErr(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  });

  useEffect(() => {
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, []);

  const consumeTarget = () => {
    setLocalTarget(null);
    setInputErr(false);
    onNewConsumed();
  };

  // ── 操作 ──────────────────────────────────────────────
  /** 新建：以 "/" 结尾 = 创建文件夹；以 ".md" 结尾 = 创建文件；其余拒绝。 */
  const submitCreate = async (dir: string, raw: string) => {
    const name = raw.trim();
    if (!name) {
      consumeTarget();
      return;
    }
    const isDir = name.endsWith("/");
    if (!isDir && !name.endsWith(".md")) {
      setInputErr(true);
      return;
    }
    const clean = isDir ? name.replace(/\/+$/, "") : name;
    const path = join(dir, clean);
    consumeTarget();
    try {
      await api.create(path, isDir ? "dir" : "file");
      expandChain(parentOf(path));
      onChanged();
      if (!isDir) onOpen(path);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  };

  const submitRename = async (node: TreeNode, raw: string) => {
    setRenaming(null);
    const name = raw.trim();
    if (!name || name === node.name) return;
    const fileName =
      node.type === "file" && !name.endsWith(".md") ? `${name}.md` : name;
    try {
      await api.move(node.path, join(parentOf(node.path), fileName));
      onChanged();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  };

  const doDelete = async (node: TreeNode) => {
    if (!confirm(`删除 ${node.path}？（将移入回收站 .trash/）`)) return;
    try {
      await api.remove(node.path);
      onChanged();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  };

  // ── 行内输入 ──────────────────────────────────────────
  const createInput = (dir: string, key: string) => (
    <li className="new-row" key={key}>
      <span className="target">{dir ? `${dir}/` : "根/"}</span>
      <input
        ref={inputRef}
        placeholder="文件名.md 或 目录名/"
        onKeyDown={(e) => {
          if (e.key === "Enter") void submitCreate(dir, e.currentTarget.value);
          if (e.key === "Escape") consumeTarget();
        }}
        onBlur={(e) => void submitCreate(dir, e.currentTarget.value)}
      />
      <span className={`hint${inputErr ? " err" : ""}`}>
        {inputErr ? "以 / 或 .md 结尾" : "↵ 创建 · Esc"}
      </span>
    </li>
  );

  const renameInput = (node: TreeNode) => (
    <li className="new-row" key={`ren-${node.path}`}>
      <span className="target">{parentOf(node.path) ? `${parentOf(node.path)}/` : "根/"}</span>
      <input
        ref={inputRef}
        defaultValue={node.name}
        onKeyDown={(e) => {
          if (e.key === "Enter") void submitRename(node, e.currentTarget.value);
          if (e.key === "Escape") setRenaming(null);
        }}
        onBlur={(e) => void submitRename(node, e.currentTarget.value)}
      />
      <span className="hint">↵ 重命名 · Esc</span>
    </li>
  );

  // ── 树渲染 ────────────────────────────────────────────
  const renderNodes = (nodes: TreeNode[], dir: string): React.ReactNode[] => {
    const items: React.ReactNode[] = [];
    if (target && target.dir === dir) {
      items.push(createInput(dir, `new-${dir}`));
    }
    for (const n of nodes) {
      if (renaming === n.path) {
        items.push(renameInput(n));
      } else if (n.type === "dir") {
        const open = expanded.has(n.path);
        items.push(
          <li key={n.path}>
            <div
              className="dir"
              onClick={(e) => {
                if ((e.target as HTMLElement).closest(".plus")) return;
                setExpanded((s) => {
                  const next = new Set(s);
                  if (next.has(n.path)) next.delete(n.path);
                  else next.add(n.path);
                  return next;
                });
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                setMenu({ x: e.clientX, y: e.clientY, node: n });
              }}
            >
              <span className="caret">{open ? "▾" : "▸"}</span>
              <span className="name">{n.name}</span>
              <span
                className="plus"
                onClick={(e) => {
                  e.stopPropagation();
                  setLocalTarget({ dir: n.path });
                }}
              >
                ＋
              </span>
            </div>
            {open && (
              <ul className="children">
                {n.children ? renderNodes(n.children, n.path) : null}
              </ul>
            )}
          </li>,
        );
      } else {
        items.push(
          <li
            key={n.path}
            className={`file${activePath === n.path ? " active" : ""}`}
            onClick={() => onOpen(n.path)}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu({ x: e.clientX, y: e.clientY, node: n });
            }}
          >
            {n.name}
          </li>,
        );
      }
    }
    return items;
  };

  return (
    <>
      <ul className="tree">{renderNodes(root.children ?? [], "")}</ul>
      {menu && (
        <div
          className="ctx-menu"
          style={{ left: menu.x, top: menu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => {
              setLocalTarget({ dir: menu.node.type === "dir" ? menu.node.path : parentOf(menu.node.path) });
              setMenu(null);
            }}
          >
            新建
          </button>
          <button
            onClick={() => {
              setRenaming(menu.node.path);
              setMenu(null);
            }}
          >
            重命名
          </button>
          <button
            className="danger"
            onClick={() => {
              setMenu(null);
              doDelete(menu.node);
            }}
          >
            删除（进回收站）
          </button>
        </div>
      )}
    </>
  );
}

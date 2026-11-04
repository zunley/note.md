/**
 * 编辑器：CodeMirror 6 + 内联预览（模式 A）/ 分栏预览（模式 B）+ 自动保存。
 * 滚动发生在编辑器内部（cm-scroller），分栏时编辑/预览按比例同步滚动。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { Autolink, Strikethrough, TaskList } from "@lezer/markdown";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

import { api, type FileContent } from "./api";
import { inlinePreview } from "./inlinePreview";
import { Preview } from "./Preview";

export type SaveStatus = "saved" | "dirty" | "saving" | "error" | "conflict";

export const STATUS_TEXT: Record<SaveStatus, string> = {
  saved: "已保存",
  dirty: "编辑中…",
  saving: "保存中…",
  error: "保存失败",
  conflict: "版本冲突",
};

const hlStyle = HighlightStyle.define([
  { tag: [t.heading1, t.heading2, t.heading3, t.heading4, t.heading5, t.heading6], class: "cm-tok-heading" },
  { tag: t.strong, class: "cm-tok-strong" },
  { tag: t.emphasis, class: "cm-tok-em" },
  { tag: t.strikethrough, class: "cm-tok-strike" },
  { tag: [t.monospace, t.special(t.monospace)], class: "cm-tok-code" },
  { tag: t.link, class: "cm-tok-link" },
  { tag: t.url, class: "cm-tok-url" },
  { tag: t.quote, class: "cm-tok-quote" },
  { tag: [t.meta, t.processingInstruction, t.comment, t.contentSeparator], class: "cm-tok-meta" },
]);

export function Editor({
  file,
  mode,
  onSaved,
  onStatusChange,
}: {
  file: FileContent;
  mode: "inline" | "split";
  onSaved: (f: FileContent) => void;
  onStatusChange?: (s: SaveStatus) => void;
}) {
  const [conflict, setConflict] = useState(false);
  const [preview, setPreview] = useState(file.content);

  const hostRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const contentRef = useRef(file.content);
  const hashRef = useRef(file.hash);
  const timerRef = useRef<number | undefined>(undefined);
  const saveRef = useRef<((force?: boolean) => Promise<void>) | undefined>(undefined);
  const statusCbRef = useRef(onStatusChange);
  statusCbRef.current = onStatusChange;

  const setStatus = useCallback((s: SaveStatus) => {
    statusCbRef.current?.(s);
  }, []);

  const save = useCallback(
    async (force = false) => {
      window.clearTimeout(timerRef.current);
      setStatus("saving");
      try {
        const r = await api.write(file.path, contentRef.current, force ? undefined : hashRef.current);
        hashRef.current = r.hash;
        setStatus("saved");
        setConflict(false);
        onSaved(r);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        const conflictNow = msg.includes("hash");
        setStatus(conflictNow ? "conflict" : "error");
        if (conflictNow) setConflict(true);
      }
    },
    [file.path, onSaved, setStatus],
  );
  saveRef.current = save;

  // 切换文件：重置编辑器内容
  useEffect(() => {
    contentRef.current = file.content;
    hashRef.current = file.hash;
    setConflict(false);
    setPreview(file.content);
    setStatus("saved");
    const view = viewRef.current;
    if (view) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: file.content },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.path]);

  // 创建编辑器（模式切换时重建，内容经 contentRef 保留）
  useEffect(() => {
    if (!hostRef.current) return;
    const view = new EditorView({
      parent: hostRef.current,
      state: EditorState.create({
        doc: contentRef.current,
        extensions: [
          history(),
          keymap.of([
            {
              key: "Mod-s",
              run: () => {
                void saveRef.current?.(true);
                return true;
              },
            },
            indentWithTab,
            ...defaultKeymap,
            ...historyKeymap,
          ]),
          markdown({
            base: markdownLanguage,
            extensions: [Strikethrough, TaskList, Autolink],
          }),
          syntaxHighlighting(hlStyle),
          inlinePreview,
          EditorView.lineWrapping,
          EditorView.updateListener.of((u) => {
            if (u.docChanged) {
              const text = u.state.doc.toString();
              contentRef.current = text;
              setPreview(text);
              setStatus("dirty");
              window.clearTimeout(timerRef.current);
              timerRef.current = window.setTimeout(() => void saveRef.current?.(), 800);
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    (window as unknown as { __cm?: EditorView }).__cm = view; // 测试钩子
    return () => {
      window.clearTimeout(timerRef.current);
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // 分栏模式：编辑 / 预览按滚动比例平滑同步（识别自发滚动防回环，不丢帧）
  useEffect(() => {
    if (mode !== "split") return;
    const a = viewRef.current?.scrollDOM;
    const b = previewRef.current;
    if (!a || !b) return;
    const ratio = (el: HTMLElement) => {
      const max = el.scrollHeight - el.clientHeight;
      return max > 0 ? el.scrollTop / max : 0;
    };
    const maxOf = (el: HTMLElement) => el.scrollHeight - el.clientHeight;
    let setA = -1; // 上次由同步写入的 scrollTop
    let setB = -1;
    const onA = () => {
      if (Math.abs(a.scrollTop - setA) < 1.5) return; // 自己触发的滚动
      setB = ratio(a) * maxOf(b);
      b.scrollTop = setB;
    };
    const onB = () => {
      if (Math.abs(b.scrollTop - setB) < 1.5) return;
      setA = ratio(b) * maxOf(a);
      a.scrollTop = setA;
    };
    a.addEventListener("scroll", onA, { passive: true });
    b.addEventListener("scroll", onB, { passive: true });
    return () => {
      a.removeEventListener("scroll", onA);
      b.removeEventListener("scroll", onB);
    };
  }, [mode]);

  const reload = async () => {
    try {
      const fresh = await api.read(file.path);
      contentRef.current = fresh.content;
      hashRef.current = fresh.hash;
      viewRef.current?.dispatch({
        changes: { from: 0, to: viewRef.current.state.doc.length, insert: fresh.content },
      });
      setPreview(fresh.content);
      setConflict(false);
      setStatus("saved");
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="editor-wrap">
      <article className={`paper${mode === "split" ? " split" : ""}`}>
        {conflict && (
          <div className="conflict">
            <b>文件已被外部修改</b>
            <span>（AI 或同步盘改动了它）</span>
            <button className="nb-btn" onClick={reload}>
              重新加载
            </button>
            <button className="nb-btn danger" onClick={() => void saveRef.current?.(true)}>
              覆盖保存
            </button>
          </div>
        )}
        <div className="panes">
          <div className="editor-host" ref={hostRef} />
          {mode === "split" && (
            <div className="preview-pane" ref={previewRef}>
              <Preview content={preview} />
            </div>
          )}
        </div>
      </article>
    </div>
  );
}

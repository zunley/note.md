/**
 * UI 真实浏览器验证（开发用，非 CI）：
 *   node src/web/tests/ui-check.mjs
 * 前置：server 已在 :8088 运行（NOTE_MD_ROOT=/tmp/note-ui NOTE_MD_PASSWORD=e2epass）。
 * 依赖：复用 files.md 的 playwright（见 require 路径）。
 */
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { chromium } = require("/home/sarto/work/source/files.md/tests/node_modules/playwright");

const results = [];
const check = (name, ok, extra = "") => {
  results.push([name, ok, extra]);
  console.log(ok ? "✓" : "✗", name, ok ? "" : extra);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));

await page.goto("http://localhost:8088/");
await page.fill('input[type="password"]', "e2epass");
await page.click(".login-card button");
await page.waitForSelector(".tree", { timeout: 8000 });
await page.click(".tree .file");
await page.waitForSelector(".cm-editor .cm-content", { timeout: 8000 });

// ── 1. 上键不跳顶 ─────────────────────────────────────────
await page.click(".cm-content");
await page.keyboard.press("Control+End");
const end = await page.evaluate(() => {
  const cm = window.__cm;
  const h = cm.state.selection.main.head;
  return { head: h, line: cm.state.doc.lineAt(h).number, total: cm.state.doc.lines };
});
await page.keyboard.press("ArrowUp");
const up1 = await page.evaluate(() => {
  const cm = window.__cm;
  const h = cm.state.selection.main.head;
  return { head: h, line: cm.state.doc.lineAt(h).number };
});
await page.keyboard.press("ArrowUp");
const up2 = await page.evaluate(() => {
  const cm = window.__cm;
  const h = cm.state.selection.main.head;
  return { head: h, line: cm.state.doc.lineAt(h).number };
});
check(
  `ArrowUp 不跳顶（末行 ${end.line} → ${up1.line} → ${up2.line}）`,
  up1.line === end.line - 1 && up2.line === end.line - 2 && up1.head > 0,
  JSON.stringify({ end, up1, up2 }),
);

// ── 2. 内联预览：标记隐藏 + 行样式 ──────────────────────────
const inline = await page.evaluate(() => {
  const hidden = document.querySelectorAll(".cm-editor .cm-content .cm-md-hidden, .cm-editor .cm-replacedContent").length;
  const h1 = document.querySelector(".cm-editor .cm-line.cm-h1");
  const h2 = document.querySelector(".cm-editor .cm-line.cm-h2");
  return {
    hasH1: !!h1,
    hasH2: !!h2,
    h1Size: h1 ? getComputedStyle(h1).fontSize : null,
    h1Margin: h1 ? getComputedStyle(h1).margin : null,
    h2Before: h2 ? getComputedStyle(h2, "::before").content : null,
  };
});
check("内联：标题行装饰存在", inline.hasH1 && inline.hasH2, JSON.stringify(inline));
check("内联：标题无 margin（margin: 0px）", inline.h1Margin === "0px", inline.h1Margin);
check("内联：h2 橙色标记存在", inline.h2Before === '""', String(inline.h2Before));
await page.keyboard.press("Control+Home");
const srcShown = await page.evaluate(() => {
  const lines = [...document.querySelectorAll(".cm-editor .cm-line")];
  const active = lines.find((el) => el.textContent.includes("记忆是思维"));
  const inactive = lines.find((el) => el.textContent.includes("本周重点"));
  const strike = lines.find((el) => el.textContent.includes("删除线"));
  return {
    active: active ? active.textContent : null,
    inactive: inactive ? inactive.textContent : null,
    strike: strike ? strike.textContent : null,
  };
});
check(
  "内联：光标行展开源码 / 非光标行隐藏标记",
  (srcShown.active ?? "").startsWith("#") && !(srcShown.inactive ?? "").includes("#"),
  JSON.stringify(srcShown),
);
check("内联：删除线标记隐藏", !(srcShown.strike ?? "").includes("~~"), String(srcShown.strike));
await page.screenshot({ path: "/tmp/ui-inline.png" });

// ── 3. 分栏：预览样式 + 同步滚动 ───────────────────────────
await page.click("text=分栏预览");
await page.waitForSelector(".preview-pane", { timeout: 4000 });
const previewStyled = await page.evaluate(() => {
  const inner = document.querySelector(".preview-pane .preview");
  const h1 = document.querySelector(".preview-pane h1");
  return {
    hasPreviewClass: !!inner,
    h1Weight: h1 ? getComputedStyle(h1).fontWeight : null,
    fontFamily: inner ? getComputedStyle(inner).fontFamily : null,
  };
});
check("分栏：预览带 .preview 样式", previewStyled.hasPreviewClass && previewStyled.h1Weight === "900", JSON.stringify(previewStyled));

await page.evaluate(() => {
  const el = document.querySelector(".cm-editor .cm-scroller");
  el.scrollTop = (el.scrollHeight - el.clientHeight) * 0.5;
});
await page.waitForTimeout(150);
const sync = await page.evaluate(() => {
  const a = document.querySelector(".cm-editor .cm-scroller");
  const b = document.querySelector(".preview-pane");
  const ratio = (el) => el.scrollTop / (el.scrollHeight - el.clientHeight || 1);
  return { a: ratio(a), b: ratio(b) };
});
check("分栏：编辑→预览 同步滚动", Math.abs(sync.a - sync.b) < 0.08, JSON.stringify(sync));

await page.evaluate(() => {
  const el = document.querySelector(".preview-pane");
  el.scrollTop = (el.scrollHeight - el.clientHeight) * 0.8;
});
await page.waitForTimeout(150);
const sync2 = await page.evaluate(() => {
  const a = document.querySelector(".cm-editor .cm-scroller");
  const b = document.querySelector(".preview-pane");
  const ratio = (el) => el.scrollTop / (el.scrollHeight - el.clientHeight || 1);
  return { a: ratio(a), b: ratio(b) };
});
check("分栏：预览→编辑 同步滚动", Math.abs(sync2.a - sync2.b) < 0.08, JSON.stringify(sync2));
await page.screenshot({ path: "/tmp/ui-split.png" });

await browser.close();
const failed = results.filter(([, ok]) => !ok);
console.log(`\n${failed.length ? "存在失败项" : "全部通过"}（${results.length - failed.length}/${results.length}）`);
process.exit(failed.length ? 1 : 0);

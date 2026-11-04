import MarkdownIt from "markdown-it";

/** 预览与 AI 回复共用的渲染器。 */
export const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  typographer: false,
});

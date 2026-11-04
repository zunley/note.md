import { md } from "./markdown";

/** 模式 B 分栏预览 / 聊天 markdown 共用渲染。 */
export function Preview({ content }: { content: string }) {
  return <div className="preview" dangerouslySetInnerHTML={{ __html: md.render(content) }} />;
}

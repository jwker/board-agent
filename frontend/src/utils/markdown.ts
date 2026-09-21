/**
 * Markdown 渲染工具：marked 转 HTML + DOMPurify 清洗（防 XSS）。
 * 用于卡片详情页的主体内容与评论流。
 */

import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({
  gfm: true, // GitHub 风格：表格、任务列表、删除线等
  breaks: true, // 单换行视为 <br>（评论流常见连续短句）
});

/** 渲染单个 Markdown 片段；空输入返回空串。 */
export function renderMarkdown(src: string): string {
  if (!src || !src.trim()) return "";
  const raw = marked.parse(src, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}

/**
 * 流式宽容渲染：AI 回复逐 token 到达时，Markdown 可能不完整
 * （代码块围栏 ``` 未闭合、表格行未写完等）。渲染前先做轻量修补，
 * 避免未闭合代码块把后续文本整体吞成代码样式造成闪跳。
 */
export function renderStreamingMarkdown(src: string): string {
  let text = src;
  // 代码块围栏：奇数个 ``` 视为未闭合，补一个收尾
  const fences = text.match(/```/g)?.length ?? 0;
  if (fences % 2 === 1) text += "\n```";
  // 行内代码反引号未配对时，丢弃最后一个裸反引号避免污染后续渲染
  const backticks = text.match(/`/g)?.length ?? 0;
  if (backticks % 2 === 1) text = text.slice(0, text.lastIndexOf("`"));
  return renderMarkdown(text);
}

/** 评论 API 与类型。 */

import { api } from "./client";

/** 工具调用步骤（AI 评论携带）：name 工具名、args 参数、status 执行中/完成、result 摘要、result_full 完整内容 */
export interface StepItem {
  index?: number;
  name: string;
  args?: unknown;
  status: "calling" | "done";
  result?: string;
  result_full?: string;
}

export interface Comment {
  id: number;
  card_id: number;
  author: "user" | "ai";
  thread_id: string | null;
  content: string;
  steps?: StepItem[] | null;
  created_at: string;
}

export function listComments(cardId: number): Promise<Comment[]> {
  return api.get<Comment[]>(`/api/cards/${cardId}/comments`);
}

export function createComment(cardId: number, content: string, modelRef?: string): Promise<Comment> {
  return api.post<Comment>(`/api/cards/${cardId}/comments`, { content, ...(modelRef ? { model_ref: modelRef } : {}) });
}

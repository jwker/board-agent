/** 评论 API 与类型。 */

import { api } from "./client";

export interface Comment {
  id: number;
  card_id: number;
  author: "user" | "ai";
  thread_id: string | null;
  content: string;
  created_at: string;
}

export function listComments(cardId: number): Promise<Comment[]> {
  return api.get<Comment[]>(`/api/cards/${cardId}/comments`);
}

export function createComment(cardId: number, content: string, modelRef?: string): Promise<Comment> {
  return api.post<Comment>(`/api/cards/${cardId}/comments`, { content, ...(modelRef ? { model_ref: modelRef } : {}) });
}

/** 卡片 API 与类型。 */

import { api } from "./client";

export type CardStatus = "backlog" | "todo" | "in_progress" | "done" | "archived";
export type CardType =
  | "requirement"
  | "bug"
  | "refactor"
  | "optimize"
  | "task"
  | "research"
  | "doc";
export type Priority = "high" | "medium" | "low";

export interface Card {
  id: number;
  project_id: number;
  title: string;
  content: string;
  card_type: CardType;
  custom_tags: string[];
  priority: Priority;
  status: CardStatus;
  acceptance_criteria: string | null;
  due_date: string | null;
  remark: string | null;
  read_only: boolean;
  archived_from: CardStatus | null;
  comment_count: number;
  execution_status: string | null;
  execution_payload: {
    actions: { name: string; args: Record<string, unknown>; description?: string }[];
    configs?: unknown[];
    saved_at?: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface CardCreate {
  title: string;
  content?: string;
  card_type?: CardType;
  custom_tags?: string[];
  priority?: Priority;
  status?: CardStatus;
  acceptance_criteria?: string | null;
  due_date?: string | null;
  remark?: string | null;
  read_only?: boolean;
}

export type CardPatch = Partial<CardCreate>;

export function listCards(projectId: number): Promise<Card[]> {
  return api.get<Card[]>(`/api/projects/${projectId}/cards`);
}

export function createCard(projectId: number, body: CardCreate): Promise<Card> {
  return api.post<Card>(`/api/projects/${projectId}/cards`, body);
}

export function getCard(id: number): Promise<Card> {
  return api.get<Card>(`/api/cards/${id}`);
}

export function updateCard(id: number, body: CardPatch): Promise<Card> {
  return api.patch<Card>(`/api/cards/${id}`, body);
}

/** 停止进行中的 AI 执行（仅 AI 处理中有效） */
export function stopCard(id: number): Promise<Card> {
  return api.post<Card>(`/api/cards/${id}/stop`);
}

/** 手动触发 AI 执行（仅进行中卡片有效，其他状态后端返回 409） */
export function executeCard(id: number, modelRef?: string): Promise<Card> {
  return api.post<Card>(`/api/cards/${id}/execute`, modelRef ? { model_ref: modelRef } : {});
}

export type ApprovalDecision = "approve" | "reject" | "edit";

/** 审批沙箱命令：批准 / 拒绝（原因）/ 编辑后执行 */
export function approveCard(
  id: number,
  body: { decision: ApprovalDecision; message?: string; command?: string },
): Promise<{ ok: boolean; status: string; message: string }> {
  return api.post(`/api/cards/${id}/approval`, body);
}

export function archiveCard(id: number): Promise<Card> {
  return api.post<Card>(`/api/cards/${id}/archive`);
}

export function restoreCard(id: number): Promise<Card> {
  return api.post<Card>(`/api/cards/${id}/restore`);
}

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

export function archiveCard(id: number): Promise<Card> {
  return api.post<Card>(`/api/cards/${id}/archive`);
}

export function restoreCard(id: number): Promise<Card> {
  return api.post<Card>(`/api/cards/${id}/restore`);
}

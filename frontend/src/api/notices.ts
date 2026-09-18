/** 通知 API。 */

import { api } from "./client";

export interface Notice {
  id: number;
  category: string;
  content: string;
  project_id: number | null;
  card_id: number | null;
  read: boolean;
  created_at: string;
}

export function listNotices(limit = 50): Promise<Notice[]> {
  return api.get<Notice[]>(`/api/notices?limit=${limit}`);
}

export function fetchUnreadCount(): Promise<{ count: number }> {
  return api.get<{ count: number }>("/api/notices/unread-count");
}

export function markNoticesRead(ids: number[]): Promise<{ count: number }> {
  return api.post<{ count: number }>("/api/notices/read", { ids });
}

export function markAllNoticesRead(): Promise<{ count: number }> {
  return api.post<{ count: number }>("/api/notices/read-all", {});
}

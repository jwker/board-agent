/** 设置 API：大模型 / 向量 / 通知 / 邮件 / 项目默认模型。 */

import { api } from "./client";

export interface LLMModelItem {
  display: string; // 显示名称
  request: string; // 实际请求模型
}

export interface LLMProvider {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  models: LLMModelItem[];
}

export interface LLMSettings {
  providers: LLMProvider[];
  default: { provider_id: string; model: string } | null;
}

export interface VectorSettings {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  dims: number;
}

export interface EmailSettings {
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_pass: string;
  from_addr: string;
  to_addr: string;
}

export function getLLMSettings(): Promise<LLMSettings> {
  return api.get<LLMSettings>("/api/settings/llm");
}

export function saveLLMSettings(body: LLMSettings): Promise<LLMSettings> {
  return api.put<LLMSettings>("/api/settings/llm", body);
}

export function addLLMProvider(body: {
  name: string;
  base_url: string;
  api_key: string;
  models: LLMModelItem[];
}): Promise<LLMSettings> {
  return api.post<LLMSettings>("/api/settings/llm/providers", body);
}

export function deleteLLMProvider(providerId: string): Promise<LLMSettings> {
  return api.delete<LLMSettings>(`/api/settings/llm/providers/${providerId}`);
}

export function updateLLMProvider(
  providerId: string,
  body: { name?: string; base_url?: string; api_key?: string; models?: LLMModelItem[] },
): Promise<LLMSettings> {
  return api.put<LLMSettings>(`/api/settings/llm/providers/${providerId}`, body);
}

export function getVectorSettings(): Promise<VectorSettings> {
  return api.get<VectorSettings>("/api/settings/vector");
}

export function saveVectorSettings(body: VectorSettings): Promise<VectorSettings> {
  return api.put<VectorSettings>("/api/settings/vector", body);
}

export function getNotificationPrefs(): Promise<Record<string, boolean>> {
  return api.get<Record<string, boolean>>("/api/settings/notification-prefs");
}

export function saveNotificationPrefs(body: Record<string, boolean>): Promise<Record<string, boolean>> {
  return api.put<Record<string, boolean>>("/api/settings/notification-prefs", body);
}

export function getEmailSettings(): Promise<EmailSettings> {
  return api.get<EmailSettings>("/api/settings/email");
}

export function saveEmailSettings(body: EmailSettings): Promise<EmailSettings> {
  return api.put<EmailSettings>("/api/settings/email", body);
}

export interface AutoClaimSettings {
  enabled: boolean;
  start_time: string;
  end_time: string;
}

export function getAutoClaim(projectId: number): Promise<AutoClaimSettings> {
  return api.get<AutoClaimSettings>(`/api/projects/${projectId}/settings/auto-claim`);
}

export function saveAutoClaim(projectId: number, body: AutoClaimSettings): Promise<AutoClaimSettings> {
  return api.put<AutoClaimSettings>(`/api/projects/${projectId}/settings/auto-claim`, body);
}

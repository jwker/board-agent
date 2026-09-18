/** 通知中心 store：未读数、列表、已读动作、WS 实时推送（轮询作断线兜底）。 */

import { ElNotification } from "element-plus";
import { ref } from "vue";

import {
  fetchUnreadCount,
  listNotices,
  markAllNoticesRead,
  markNoticesRead,
  type Notice,
} from "../api/notices";
import { connect, onWS, type WSMessage } from "../api/ws";

const notices = ref<Notice[]>([]);
const unreadCount = ref(0);
const drawerOpen = ref(false);
const loading = ref(false);
let pollTimer: number | null = null;
let lastSeenNewestId = 0;
let pollActive = false;

const CATEGORY_LABELS: Record<string, string> = {
  approval_waiting: "等待人工审批",
  completed: "AI 处理完成",
  failed: "任务失败",
  timeout_rejected: "审批超时已拒绝",
  clarify: "需要澄清",
};

function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

async function refreshUnread(): Promise<void> {
  try {
    const { count } = await fetchUnreadCount();
    unreadCount.value = count;
  } catch {
    /* 服务未就绪时静默 */
  }
}

async function refreshList(): Promise<void> {
  loading.value = true;
  try {
    notices.value = await listNotices();
    if (notices.value.length > 0) {
      lastSeenNewestId = Math.max(lastSeenNewestId, notices.value[0].id);
    }
  } finally {
    loading.value = false;
  }
}

async function openDrawer(): Promise<void> {
  drawerOpen.value = true;
  await refreshList();
  await refreshUnread();
}

function closeDrawer(): void {
  drawerOpen.value = false;
}

async function readOne(n: Notice): Promise<void> {
  if (!n.read) {
    await markNoticesRead([n.id]);
    n.read = true;
    await refreshUnread();
  }
}

async function readAll(): Promise<void> {
  await markAllNoticesRead();
  notices.value.forEach((n) => (n.read = true));
  unreadCount.value = 0;
}

function notifyUI(n: Notice): void {
  ElNotification({
    title: categoryLabel(n.category),
    message: n.content,
    type: n.category === "failed" ? "error" : n.category === "approval_waiting" ? "warning" : "success",
    duration: 6000,
    onClick: () => {
      if (n.card_id) {
        window.dispatchEvent(
          new CustomEvent("notice-jump", {
            detail: { projectId: n.project_id, cardId: n.card_id },
          }),
        );
      }
    },
  });
}

/** 轮询（WS 断线兜底）：未读数变化或出现新 ID 时弹站内提示。 */
function startPolling(intervalMs = 15000): void {
  stopPolling();
  pollActive = true;
  pollTimer = window.setInterval(async () => {
    try {
      const { count } = await fetchUnreadCount();
      if (count > unreadCount.value) {
        const fresh = await listNotices(5);
        for (const n of fresh) {
          if (n.id <= lastSeenNewestId || n.read) continue;
          lastSeenNewestId = Math.max(lastSeenNewestId, n.id);
          notifyUI(n);
        }
        unreadCount.value = count;
      } else if (count < unreadCount.value) {
        unreadCount.value = count;
      }
    } catch {
      /* 网络抖动静默 */
    }
  }, intervalMs);
}

function stopPolling(): void {
  pollActive = false;
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function onNotificationMessage(msg: WSMessage): void {
  const payload = msg.payload as {
    notice_id?: number;
    category?: string;
    content?: string;
    project_id?: number | null;
    card_id?: number | null;
  };
  if (!payload || payload.notice_id === undefined) return;
  if (payload.notice_id <= lastSeenNewestId) return;
  lastSeenNewestId = Math.max(lastSeenNewestId, payload.notice_id);
  unreadCount.value += 1;
  notifyUI({
    id: payload.notice_id,
    category: payload.category ?? "",
    content: payload.content ?? "",
    project_id: payload.project_id ?? null,
    card_id: payload.card_id ?? null,
    read: false,
    created_at: new Date().toISOString(),
  });
}

/** 启动 WS 主通道 + 断线轮询兜底 + 重连后全量刷新。 */
function setupWS(): () => void {
  connect();
  const offNotification = onWS("notification", onNotificationMessage);

  const onStatus = (e: Event) => {
    const online = (e as CustomEvent<{ online: boolean }>).detail.online;
    if (online) {
      stopPolling();
      refreshUnread(); // 重连后全量重拉（当前视图由页面监听 ws-reconnected 刷新）
      window.dispatchEvent(new CustomEvent("ws-reconnected"));
    } else {
      startPolling(); // 断线期间轮询兜底
    }
  };
  window.addEventListener("ws-status", onStatus);

  return () => {
    offNotification();
    window.removeEventListener("ws-status", onStatus);
    stopPolling();
  };
}

export function useNoticeStore() {
  return {
    notices,
    unreadCount,
    drawerOpen,
    loading,
    categoryLabel,
    openDrawer,
    closeDrawer,
    readOne,
    readAll,
    startPolling,
    stopPolling,
    setupWS,
    refreshUnread,
  };
}

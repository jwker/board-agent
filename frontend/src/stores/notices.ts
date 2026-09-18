/** 通知中心 store：未读数、列表、已读动作、轮询与弹窗。 */

import { ElNotification } from "element-plus";
import { computed, ref } from "vue";

import {
  fetchUnreadCount,
  listNotices,
  markAllNoticesRead,
  markNoticesRead,
  type Notice,
} from "../api/notices";

const notices = ref<Notice[]>([]);
const unreadCount = ref(0);
const drawerOpen = ref(false);
const loading = ref(false);
let pollTimer: number | null = null;
let lastSeenNewestId = 0;

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

/** 轮询新通知：未读数变化或出现新 ID 时弹站内提示。 */
function startPolling(intervalMs = 15000): void {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    try {
      const { count } = await fetchUnreadCount();
      if (count > unreadCount.value) {
        // 有新增未读 → 拉最新通知弹窗
        const fresh = await listNotices(5);
        for (const n of fresh) {
          if (n.id <= lastSeenNewestId || n.read) continue;
          lastSeenNewestId = Math.max(lastSeenNewestId, n.id);
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
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
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
    refreshUnread,
  };
}

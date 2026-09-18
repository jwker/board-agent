/** WebSocket 客户端（TECH-DESIGN §4）：全局单连接、指数退避重连、事件分发。 */

export interface WSMessage {
  type: string;
  payload: Record<string, unknown>;
}

type Handler = (msg: WSMessage) => void;

const handlers = new Map<string, Set<Handler>>();
let socket: WebSocket | null = null;
let closedByUser = false;
let retryCount = 0;
let reconnectTimer: number | null = null;

const WS_URL = () => {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
};

function scheduleReconnect(): void {
  if (closedByUser) return;
  const delay = Math.min(1000 * 2 ** retryCount, 30000); // 1s → 2s → 4s … 上限 30s
  retryCount += 1;
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  reconnectTimer = window.setTimeout(() => connect(), delay);
}

export function connect(): void {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
  try {
    socket = new WebSocket(WS_URL());
  } catch {
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    retryCount = 0;
    window.dispatchEvent(new CustomEvent("ws-status", { detail: { online: true } }));
  };

  socket.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as WSMessage;
      const set = handlers.get(msg.type);
      if (set) for (const h of set) h(msg);
    } catch {
      /* 忽略无法解析的消息 */
    }
  };

  socket.onclose = () => {
    socket = null;
    window.dispatchEvent(new CustomEvent("ws-status", { detail: { online: false } }));
    scheduleReconnect();
  };

  socket.onerror = () => {
    socket?.close();
  };
}

export function disconnect(): void {
  closedByUser = true;
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  socket?.close();
  socket = null;
}

export function onWS(type: string, handler: Handler): () => void {
  if (!handlers.has(type)) handlers.set(type, new Set());
  handlers.get(type)!.add(handler);
  return () => handlers.get(type)?.delete(handler);
}

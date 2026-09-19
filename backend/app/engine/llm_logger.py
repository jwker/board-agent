"""LLM 调用入参/出参日志（调试用，控制台结构化输出）。

挂在模型实例上，所有大模型调用（执行 agent 内部调用、工具模型标题提炼等）
都会打印清晰的请求（逐条消息）/ 返回（tokens+内容）/ 错误。
"""

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

logger = logging.getLogger("app.llm")

# 单条消息打印上限：任务指令含评论流可能上千字，4000 保证对话内容完整可见；
# system prompt（L1 简报）超长时仍截断避免刷屏，并标注总长
CONTENT_LIMIT = 4000

BOX = "  "  # 内容行缩进


def _fmt_content(content: Any, limit: int = CONTENT_LIMIT) -> str:
    """消息内容转可打印文本：兼容 str / content blocks（list[dict]）。"""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or str(block))
            else:
                parts.append(str(block))
        text = "\n".join(parts)
    else:
        text = "" if content is None else str(content)
    if len(text) > limit:
        return f"{text[:limit]}…（截断，总长 {len(text)}）"
    return text


def _fmt_tool_calls(tool_calls: Any) -> str:
    if not tool_calls:
        return ""
    parts = []
    for tc in tool_calls:
        name = tc.get("name", "?")
        args = tc.get("args")
        parts.append(f"  ↳ {name}({args})")
    return "\n".join(parts)


def _msg_role(m: BaseMessage) -> str:
    return m.type


def _fmt_msg(m: BaseMessage, idx: int) -> str:
    """格式化单条消息：角色 + 名称/工具调用ID + 内容 + 工具调用。"""
    head = f"[{idx}] {_msg_role(m)}"
    extra = []
    if getattr(m, "name", None):
        extra.append(f"name={m.name}")
    if getattr(m, "tool_call_id", None):
        extra.append(f"tool_call_id={m.tool_call_id}")
    if extra:
        head += f" ({', '.join(extra)})"
    lines = [head]
    content = _fmt_content(getattr(m, "content", ""))
    if content:
        lines.append(f"{BOX}{content}")
    tcs = _fmt_tool_calls(getattr(m, "tool_calls", None))
    if tcs:
        lines.append(f"{BOX}{tcs}")
    return "\n".join(lines)


class LLMLogHandler(BaseCallbackHandler):
    """每次 LLM 调用的入参（逐条角色+内容）、出参（tokens+内容）与错误。"""

    raise_error = False

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list[list[BaseMessage]],
        **kwargs: Any,
    ) -> None:
        model = (kwargs.get("invocation_params") or {}).get("model") or serialized.get("name", "?")
        msgs = messages[0] if messages else []
        logger.info("─" * 12 + " LLM 请求 " + "─" * 12)
        logger.info("  model    : %s", model)
        logger.info("  messages : %d", len(msgs))
        for i, m in enumerate(msgs, 1):
            for line in _fmt_msg(m, i).split("\n"):
                logger.info("%s%s", BOX, line)
        logger.info("─" * 32)

    def on_llm_end(self, response, **kwargs: Any) -> None:
        logger.info("─" * 12 + " LLM 返回 " + "─" * 12)
        if getattr(response, "generations", None) and response.generations:
            msg = response.generations[0][0].message
            usage = getattr(msg, "usage_metadata", None) or {}
            if usage:
                logger.info(
                    "  tokens   : input=%s output=%s total=%s",
                    usage.get("input_tokens", "?"),
                    usage.get("output_tokens", "?"),
                    usage.get("total_tokens", "?"),
                )
            content = _fmt_content(msg.content)
            if content:
                logger.info("  content  : %s", content)
            tcs = _fmt_tool_calls(getattr(msg, "tool_calls", None))
            if tcs:
                logger.info("  tool_calls:")
                for line in tcs.split("\n"):
                    logger.info("%s%s", BOX, line)
        else:
            logger.info("  （空响应）")
        logger.info("─" * 32)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        logger.error("─" * 12 + " LLM 错误 " + "─" * 12)
        logger.error("  %s: %s", type(error).__name__, str(error)[:500])
        logger.error("─" * 32)


llm_logger = LLMLogHandler()

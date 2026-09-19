"""轻量标题总结器（3.1 补项 · 异步版）。

设计：标题总结是**单次裸 LLM 调用**，不走 Deep Agents harness
（无工具、无多轮、无规划，create_deep_agent 对其过重）。
独立成模块，自带超时与降级，保证任何失败都不影响建卡。
"""

import asyncio
import logging

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

_MAX_TITLE_LEN = 24
_FALLBACK_LEN = 20
_TIMEOUT_S = 15  # 标题任务超时：超过直接走兜底，不阻塞、不无限等

TITLE_PROMPT = (
    "你是一个标题提取器。把下面的任务内容总结成一个中文卡片标题。"
    "规则：1) 不超过{limit}个字；2) 保留关键动作与对象；3) 直接输出标题本身，"
    "不要解释、不要引号、不要标点结尾、不要输出\"标题：\"等前缀。\n\n{content}"
)


def fallback_title(content: str) -> str:
    """兜底：取内容首段前 20 字（无模型 / 超时 / 失败时立即使用）。"""
    text = (content or "").strip().replace("\n", " ")
    if not text:
        return "未命名卡片"
    return text[:_FALLBACK_LEN] + ("…" if len(text) > _FALLBACK_LEN else "")


def _extract_title(resp) -> str:
    """兼容推理模型：content 为空时退回 reasoning_content 末段。"""
    content = (getattr(resp, "content", None) or "").strip()
    if content:
        return " ".join(content.split())
    # DeepSeek R1 等推理模型可能只在 reasoning_content 输出
    reasoning = getattr(resp, "reasoning_content", None) or ""
    if reasoning:
        # 思考内容以"最终答案"结尾，取最后一段作为候选
        text = " ".join(reasoning.strip().split())
        tail = text[-_MAX_TITLE_LEN * 4 :]
        return " ".join(tail.split())
    return ""


async def summarize_title(content: str, model: BaseChatModel) -> str:
    """单次调用总结标题（≤24 字）；超时/失败/空结果一律回落 fallback_title。"""
    prompt = TITLE_PROMPT.format(limit=_MAX_TITLE_LEN, content=content)
    try:
        resp = await asyncio.wait_for(model.ainvoke([("user", prompt)]), timeout=_TIMEOUT_S)
        title = _extract_title(resp)
        if not title:
            return fallback_title(content)
        return title[:_MAX_TITLE_LEN]
    except TimeoutError:
        logger.warning("标题总结超时（>%ss），使用兜底", _TIMEOUT_S)
        return fallback_title(content)
    except Exception as e:  # noqa: BLE001 - LLM 失败不阻断建卡
        logger.warning("标题总结失败，使用兜底标题: %s", e)
        return fallback_title(content)

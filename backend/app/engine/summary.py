"""收尾总结器（3.5）：卡片拖到"已完成"时注入"仅总结不执行"提示词。

设计：收尾总结是**单次裸 LLM 调用**（同标题精修模式，不走 Deep Agents harness），
保证 AI 在收尾时绝不执行卡片任务、不调用任何工具——
特别是积压/待办直接拖到已完成、AI 一次对话都没发生过的情况，
没有本提示词约束，AI 可能把"已完成"当成任务去开工。
"""

import asyncio
import logging

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

_TIMEOUT_S = 30  # 总结任务超时：超过直接放弃，不阻塞状态迁移
_MAX_SUMMARY_LEN = 300

COMPLETION_PROMPT = (
    "这张卡片已被标记为【已完成】。你只需要做一件事：基于下面的卡片内容和讨论记录，"
    "用中文输出一段简洁的完成总结。\n"
    "要求：\n"
    "1) 概括这项工作做了什么、结果如何；如有遗留问题或未完成事项，一并说明；\n"
    "2) 不超过 150 字；\n"
    "3) 直接输出总结正文，不要加\"总结：\"等前缀；\n"
    "4) 【重要】不要执行任何任务、不要调用任何工具、不要做任何额外动作。\n\n"
    "卡片标题：{title}\n"
    "卡片内容：{content}\n"
    "讨论记录：\n{comments}"
)


def build_comments_text(comments) -> str:
    """把评论流转成可读的讨论记录（[用户]/[AI] 前缀，倒序截断）。"""
    if not comments:
        return "（无）"
    lines = []
    for c in comments[-40:]:  # 最近 40 条，保证上下文可控
        who = "AI" if getattr(c, "author", "") == "ai" else "用户"
        text = (c.content or "").strip().replace("\n", " ")
        if not text:
            continue
        lines.append(f"[{who}] {text[:200]}")
    return "\n".join(lines) if lines else "（无）"


def _extract_summary(resp) -> str:
    """兼容推理模型：content 为空时退回 reasoning_content 末段。"""
    content = (getattr(resp, "content", None) or "").strip()
    if content:
        return " ".join(content.split())
    reasoning = getattr(resp, "reasoning_content", None) or ""
    if reasoning:
        return " ".join(reasoning.strip().split())
    return ""


async def summarize_completion(card, comments, model: BaseChatModel) -> str:
    """单次调用生成完成总结（≤150 字）；超时/失败/空结果返回空串（调用方放弃回帖）。"""
    prompt = COMPLETION_PROMPT.format(
        title=card.title or "（无标题）",
        content=(card.content or "")[:1000],
        comments=build_comments_text(comments),
    )
    try:
        resp = await asyncio.wait_for(model.ainvoke([("user", prompt)]), timeout=_TIMEOUT_S)
        summary = _extract_summary(resp)
        if not summary:
            logger.info("收尾总结为空，放弃回帖")
            return ""
        return summary[:_MAX_SUMMARY_LEN]
    except TimeoutError:
        logger.warning("收尾总结超时（>%ss），放弃回帖", _TIMEOUT_S)
        return ""
    except Exception as e:  # noqa: BLE001 - 收尾失败不影响状态迁移
        logger.warning("收尾总结调用失败：%s", e)
        return ""

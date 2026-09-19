"""场景提示词：L1 简报组装（TECH-DESIGN §3 上下文组装 ①）。

简报三部分：项目介绍 + 卡片索引 + AGENT.md 规范，注入 system prompt，
让 AI 执行任务前掌握项目整体与其他卡片进展。
"""

from app.db.enums import CardStatus, CommentAuthor
from app.db.models import Card, Project

# 卡片索引中"一句话结果"最大长度
CARD_INDEX_RESULT_MAX = 80
# 简报卡片上限（防止简报过长挤占上下文）
CARD_INDEX_LIMIT = 50


def _card_result(card: Card) -> str:
    """取卡片"一句话结果"：最后一条 AI 评论的内容截断为单行。"""
    ai_comments = [c for c in card.comments if c.author == CommentAuthor.AI.value]
    if not ai_comments:
        return ""
    text = ai_comments[-1].content.strip().replace("\n", " ")
    return text[:CARD_INDEX_RESULT_MAX]


def build_briefing(project: Project, cards: list[Card]) -> str:
    """组装 L1 简报：项目介绍 + 卡片索引 + AGENT.md 规范。

    - cards: 项目下全部卡片（未归档优先；超过上限截断并标注）
    - 卡片索引：标题 + 状态 + 一句话结果（取最后一条 AI 评论，无则省略）
    """
    parts: list[str] = ["【项目】"]
    parts.append(f"名称：{project.name}")
    if project.description:
        parts.append(f"介绍：{project.description}")

    parts.append("【项目规范（AGENT.md）】")
    if project.agent_md:
        parts.append(project.agent_md.strip())
    else:
        parts.append("（未设置项目规范）")

    active = [c for c in cards if c.status != CardStatus.ARCHIVED.value]
    if not active:
        active = cards
    parts.append("【项目卡片索引】")
    if not active:
        parts.append("（暂无卡片）")
    else:
        shown = active[:CARD_INDEX_LIMIT]
        for c in shown:
            result = _card_result(c)
            line = f"- #{c.id} [{c.status}] {c.title}"
            if result:
                line += f"：{result}"
            parts.append(line)
        if len(active) > CARD_INDEX_LIMIT:
            parts.append(f"（另有 {len(active) - CARD_INDEX_LIMIT} 张卡片未列出）")
    return "\n".join(parts)


def build_system_prompt(project: Project, cards: list[Card]) -> str:
    """基础执行提示词 + L1 简报（3.2 简报注入）。"""
    from app.engine.agent import BASE_SYSTEM_PROMPT

    parts = []
    if BASE_SYSTEM_PROMPT.strip():
        parts.append(BASE_SYSTEM_PROMPT.strip())
    parts.append("==== 项目简报 ====")
    parts.append(build_briefing(project, cards))
    return "\n\n".join(parts)

"""通知假数据种子脚本（验证 2.5 通知中心 UI）。

用法：cd backend && uv run python scripts/seed_notices.py
会向开发库 board 插入五类通知各 1-2 条（绑定现有项目/卡片），
较早的几条标记为已读。可重复运行（每次插入一批）。
"""

import asyncio

from sqlalchemy import select

from app.db.deps import SessionFactory
from app.db.enums import NoticeCategory
from app.db.models import Card, Notice, Project
from app.services.notice_service import notify

CARD_TITLES = ["登录页白屏排查", "AI 自动领取任务开关", "卡片拖拽优化"]


async def main() -> None:
    async with SessionFactory() as s:
        project = (
            await s.execute(select(Project).order_by(Project.id.desc()))
        ).scalars().first()
        if project is None:
            print("没有项目，先建项目再跑种子脚本")
            return
        cards = (
            await s.execute(
                select(Card).where(Card.project_id == project.id).order_by(Card.id.desc())
            )
        ).scalars().all()
        card_ids = [c.id for c in cards] or [None] * 3
        pid = project.id

        rows = [
            (
                NoticeCategory.APPROVAL_WAITING.value,
                f"卡片「{CARD_TITLES[0]}」等待人工审批：AI 已修改 3 个文件，需要你确认是否应用改动。",
                pid,
                card_ids[0],
            ),
            (
                NoticeCategory.COMPLETED.value,
                f"卡片「{CARD_TITLES[1]}」AI 处理完成：已生成摘要并自动提交代码。",
                pid,
                card_ids[1],
            ),
            (
                NoticeCategory.FAILED.value,
                f"卡片「{CARD_TITLES[2]}」任务失败：运行测试时出现 2 个用例失败，请查看详情。",
                pid,
                card_ids[2],
            ),
            (
                NoticeCategory.TIMEOUT_REJECTED.value,
                f"卡片「{CARD_TITLES[0]}」审批超时未处理，改动已自动拒绝并回滚。",
                pid,
                card_ids[0],
            ),
            (
                NoticeCategory.CLARIFY.value,
                f"卡片「{CARD_TITLES[1]}」需要澄清：验收标准未填写，AI 无法开始执行。",
                pid,
                card_ids[1],
            ),
            (
                NoticeCategory.COMPLETED.value,
                f"项目「{project.name}」阶段 2 已全部完成，共 2 张卡片收尾。",
                pid,
                None,
            ),
            (
                NoticeCategory.APPROVAL_WAITING.value,
                f"卡片「{CARD_TITLES[2]}」等待人工审批：沙箱执行了 git push 命令，需要你确认。",
                pid,
                card_ids[2],
            ),
        ]

        created = []
        for category, content, cpid, cid in rows:
            n = await notify(
                s, category=category, content=content, project_id=cpid, card_id=cid, force=True
            )
            if n:
                created.append(n)

        # 最早两条标为已读，模拟看过的历史通知
        if len(created) >= 2:
            for n in created[:2]:
                n.read = True
            await s.commit()

        print(f"已插入 {len(created)} 条通知（项目 {pid}，卡片 {card_ids}），前 2 条标记已读")


asyncio.run(main())

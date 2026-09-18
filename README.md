# 看板 Agent

本地 AI 编程看板：看板上的每条卡片（需求 / bug / 重构 / 优化 / 任务 / 调研 / 文档）都是一次 AI 任务，AI 用 LangChain Deep Agents 引擎在本地授权目录内编写代码。表面是看板，本质是一个驱动 AI 的 agent 项目。

## 当前状态

规划阶段已完成，正在开发中（阶段 0 · 项目架构搭建）。

## 文档

| 文档 | 位置 | 说明 |
|---|---|---|
| 产品需求 | `.ai/prd/PRD-v0.2.md` | 做什么 |
| 需求决策 | `.ai/plans/initial-requirements.md` | A/B/C/D 组定案依据 |
| 技术方案 | `.ai/tech/TECH-DESIGN-v0.1.md` | 怎么做 |
| 技术栈 | `.ai/tech/TECH-STACK-v0.1.md` | 用什么 |
| 测试方案 | `.ai/tech/TEST-PLAN-v0.1.md` | 怎么验 |
| 开发计划 | `.ai/tech/DEV-PLAN-v0.1.md` | 五阶段路线 |
| 原型 | `.ai/plans/prototype/` | 10 页界面原型 |

## 快速开始

```bash
make setup          # 初始化：装依赖 + 复制 .env.example → .env
make db-up          # 起 PG + Milvus（Docker Compose，仅基础设施）
make migrate        # Alembic 建表
make dev            # 启动前后端（后端 uvicorn + 前端 Vite）
```

环境要求：Python 3.12+、Node.js 20+、uv、pnpm、Docker。

## 约定

- `git` 提交遵循：说"提交"只 commit 不 push；说"推送"才 push
- `.ai/` 是 AI 协作数据目录，纳入版本库管理（含对话日志、需求、原型、文档）

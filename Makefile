# 看板 Agent · 统一命令入口
# 用法见 .ai/tech/TECH-DESIGN-v0.1.md §6.1

.PHONY: setup db-up db-down db-reset migrate migrate-down dev dev-backend dev-frontend build serve test test-unit test-api test-engine lint fmt vec-rebuild clean doctor

BACKEND := backend
FRONTEND := frontend

## 初始化：装依赖 + 生成 .env（已存在则跳过）
setup:
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && pnpm install
	@test -f .env || cp .env.example .env
	@echo "setup done. 按需执行 make db-up && make migrate"

## 基础设施（本机已有 OrbStack 实例时无需执行，见 .env 注释）
db-up:
	docker compose up -d

db-down:
	docker compose down

## 开发期清空重建（危险，仅开发库用）
db-reset:
	docker compose down -v

## 迁移
migrate:
	cd $(BACKEND) && uv run alembic upgrade head

migrate-down:
	cd $(BACKEND) && uv run alembic downgrade -1

## 本地开发：仅后端 :8000（--reload）
dev-backend:
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000

## 本地开发：仅前端 :5173
dev-frontend:
	cd $(FRONTEND) && pnpm dev

## 本地开发：后端 + 前端并行
dev:
	bash -c 'cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000 & cd $(FRONTEND) && pnpm dev & wait'

## 前端生产构建
build:
	cd $(FRONTEND) && pnpm build

## 生产形态：单进程 FastAPI（static 托管在阶段 4 接入）
serve:
	cd $(BACKEND) && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

## 测试（前端/引擎分组随测试基建落地后补充）
test:
	cd $(BACKEND) && uv run pytest

test-unit:
	cd $(BACKEND) && uv run pytest tests/test_unit -q

test-api:
	cd $(BACKEND) && uv run pytest tests/test_api -q

test-engine:
	@echo "阶段 3 接入：AI 引擎测试"

## 代码质量（后端 ruff；前端 eslint/prettier 后续接入）
lint:
	cd $(BACKEND) && uv run ruff check .

fmt:
	cd $(BACKEND) && uv run ruff format .

## 手动触发向量全量重建（阶段 4 实现）
vec-rebuild:
	@echo "阶段 4 实现：从 PG 重放重建 Milvus 索引"

## 清理缓存与测试残留（不动业务数据）
clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(FRONTEND)/dist

## 环境健康检查：PG / Milvus / 迁移状态
doctor:
	cd $(BACKEND) && uv run python -m scripts.doctor

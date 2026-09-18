-- 看板 Agent · PG 首次初始化脚本（postgres 镜像仅在空数据卷时执行）
-- board 库由 compose 环境变量 POSTGRES_DB 自动创建，这里补建测试库
CREATE DATABASE board_test;

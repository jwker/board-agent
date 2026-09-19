"""3.4 沙箱最小版：自定义命令沙箱后端（命令四道关卡 + 授权目录映射）。

设计（TECH-DESIGN §5）：
- 文件读写：virtual_mode=True + root_dir=授权目录，Deep Agents 文件工具自动限定在目录内。
- 命令执行 execute()：每条命令过四道关卡
    1. 白名单直接跑（测试/构建/静态检查/只读 git/包安装/只读探查）
    2. 黑名单直接拒（rm -rf / curl·wget 任意 / sudo / git push / chmod 等）
    3. 其余 interrupt 挂起人工审批（由 HumanInTheLoopMiddleware 的 when 谓词在调用前拦截）
    4. 单条命令超时默认 300s，超时强杀（subprocess start_new_session 杀进程组）
- 环境：不继承父进程环境变量（剥离 API key 等敏感值），仅注入最小 PATH/HOME。
"""

import shlex
from pathlib import Path

from deepagents.backends.local_shell import LocalShellBackend
from deepagents.backends.sandbox import ExecuteResponse
from langchain.agents.middleware import InterruptOnConfig
from langchain.agents.middleware.types import ToolCallRequest

# 单命令超时默认 5 分钟（TECH-DESIGN §5 第 4 关）
DEFAULT_CMD_TIMEOUT = 300

# ---------- 白名单：测试/构建/静态检查/只读 git/包安装/只读探查 ----------
_WHITELIST_PREFIXES: tuple[str, ...] = (
    # 测试与构建
    "pytest",
    "uv run pytest",
    "python -m pytest",
    "make test",
    "make build",
    "make",
    "pnpm test",
    "pnpm build",
    "npm test",
    "npm run build",
    # 静态检查
    "ruff check",
    "ruff format --check",
    "vue-tsc --noEmit",
    "tsc --noEmit",
    "eslint",
    # 依赖安装
    "pip install",
    "uv pip install",
    "uv sync",
    "uv add",
    "pnpm install",
    "pnpm add",
    "npm install",
    "npm install",
    # 只读 git
    "git status",
    "git diff",
    "git log",
    "git show",
    "git branch",
    "git fetch",
    "git ls-files",
    "git stash list",
    "git rev-parse",
    # 只读探查
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "echo",
    "which",
    "file",
    "du",
    "df",
    "tree",
    "python -c",
    "uv run python",
)

# ---------- 黑名单：危险/破坏性/外发网络（子串匹配，先于白名单判定） ----------
_BLACKLIST_PATTERNS: tuple[str, ...] = (
    # 危险删除
    "rm -rf", "rm -fr", "rm -r -f", "rm -rf", "rm -f --",
    # 外发网络 / 任意下载
    "curl", "wget",
    # 提权 / 系统级
    "sudo", "su root", "chmod", "chown", "mkfs", "fdisk", "dd if=",
    "shutdown", "reboot", "halt", "poweroff",
    # 进程与系统杀伤
    "killall", "pkill -9", "kill -9",
    # git 写远端
    "git push", "git remote set-url", "git config --global",
    # 远程接入 / 端口扫描
    "ssh ", "scp ", "rsync ", "nmap", "netcat", "nc -",
    # 明文泄密 / 脚本注入
    ">/dev/sda", "> /dev/sd",
    "eval ", "exec(",
    ":(){", "(){",
    # 敏感文件（凭据/系统文件；项目内 .env 不在此列）
    "security find-generic-password",
    ".ssh/", "id_rsa", "id_ed25519",
    "/etc/passwd", "/etc/shadow", "/etc/sudoers", "/var/root",
)


def _normalize(command: str) -> str:
    """去掉首尾空白并压缩连续空白（便于前缀匹配）。"""
    return " ".join(command.strip().split())


def _is_blacklisted(command: str) -> bool:
    """黑名单：整条命令（小写）命中任一危险子串即拒绝。"""
    lowered = command.lower()
    return any(p in lowered for p in _BLACKLIST_PATTERNS)


def is_whitelisted(command: str) -> bool:
    """白名单：首命令在前缀表中（带边界），且整条命令未命中黑名单。"""
    if _is_blacklisted(command):
        return False
    normalized = _normalize(command)
    if not normalized:
        return False
    # 前 3 个 token 拼出的前缀做匹配（如 "uv run pytest -x"）
    tokens = shlex.split(normalized)[:3]
    prefix = " ".join(tokens)
    for wl in _WHITELIST_PREFIXES:
        if prefix == wl or prefix.startswith(wl + " "):
            return True
    # 单 token 命令（ls/cat/pwd/...）
    first = tokens[0]
    return any(first == wl for wl in _WHITELIST_PREFIXES)


def should_interrupt_command(command: str) -> bool:
    """四道关卡的路由：白名单放行（False=不审批）、黑名单放行到执行层拒绝（False）、其余挂起审批（True）。"""
    if not command or not command.strip():
        return False
    return not is_whitelisted(command) and not _is_blacklisted(command)


def _execute_when(request: ToolCallRequest) -> bool:
    """HumanInTheLoopMiddleware 的 when 谓词：命中"其余"的命令才 interrupt。

    tool_call 是 TypedDict（dict 语义），按 dict 访问兼容各种调用方。
    """
    try:
        tool_call = request.tool_call
        args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
        command = str((args or {}).get("command", "") or "")
    except Exception:  # noqa: BLE001 - 解析异常按需审批，安全优先
        return True
    return should_interrupt_command(command)


def build_execute_interrupt_config() -> InterruptOnConfig:
    """execute 工具的审批配置：批准 / 拒绝（附原因）/ 编辑命令。"""
    return InterruptOnConfig(
        allowed_decisions=["approve", "reject", "edit"],
        when=_execute_when,
    )


class CommandSandboxBackend(LocalShellBackend):
    """授权目录内的本地命令沙箱。

    - root_dir：项目授权目录（文件工具与命令 cwd 均限定在此目录）
    - 白名单命令直接执行（干净环境，不继承父进程变量）
    - 黑名单命令直接拒绝（exit 1 + 原因）
    - 其余命令理论不会到达执行层（when 谓词已挂起审批），兜底仍拒绝
    - 超时默认 300s，超时强杀进程组
    """

    def __init__(
        self,
        root_dir: str | Path,
        env: dict[str, str] | None = None,
        timeout: int = DEFAULT_CMD_TIMEOUT,
    ) -> None:
        home = str(Path.home())
        path_dirs = ["/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/opt/homebrew/bin"]
        # 用父进程 PATH 定位常用工具的真实目录（uv/python/node 等），只取目录不继承全部 PATH
        import shutil

        for exe in ("uv", "python3", "python", "node", "pnpm", "npm", "make", "git", "pytest"):
            found = shutil.which(exe)
            if found:
                d = str(Path(found).resolve().parent)
                if d not in path_dirs:
                    path_dirs.append(d)
        clean_env = {
            "PATH": ":".join(path_dirs),
            "HOME": home,
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "PYTHONUNBUFFERED": "1",
            "TERM": "dumb",
        }
        if env:
            clean_env.update(env)
        super().__init__(
            root_dir=str(root_dir),
            virtual_mode=True,
            timeout=timeout,
            max_output_bytes=200_000,
            env=clean_env,
            inherit_env=False,
        )

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        if not command or not command.strip():
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )
        if _is_blacklisted(command):
            return ExecuteResponse(
                output=(
                    "[sandbox] 命令被黑名单拒绝（违反安全策略）。"
                    "如需执行请改用白名单命令或拆分为多步安全命令。"
                ),
                exit_code=1,
                truncated=False,
            )
        if not is_whitelisted(command):
            return ExecuteResponse(
                output=(
                    "[sandbox] 命令不在白名单，应经人工审批后执行。"
                    "若本命令已通过审批却仍被拒，请重新发起执行。"
                ),
                exit_code=1,
                truncated=False,
            )
        return super().execute(command, timeout=timeout)

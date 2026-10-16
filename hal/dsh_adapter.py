"""DSH（DeepSeek Harness）适配器。

契约基线（官方仓库 deepseek-ai/deepseek-harness，MIT，developer preview）：
    dsh [--profile] <name> [options] [app-args...]
      -V, --version                  输出版本号
      --profile <name>               启动 $DSH_HOME/profiles 下的 profile
      --from-default-profile <name>  用出厂模板重建自定义 profile
      --patch <path>                 在 profile 层之上叠加 patch-list 覆盖（可重复）
      --dump-config / --dump-config-schema / --dump-default-config
    出厂 profile：web / headless / sdk / sdk-minimal / acp
    dsh --profile headless --json "<task>"          NDJSON 运行事件流
    dsh --profile headless --session-id <id> "..."  接管已持久化 Session（未知 id 报错）
    MCP（@deepseek-ai/dsh-mcp-client，StdioConfig）：transport / serverName / command / args /
      env / cwd / toolCallTimeoutMs / failOnStartupError；模型可见工具名 mcp__<serverName>__<rawName>

工程纪律（design-blueprint.md §2.1）：
- 本模块是全项目唯一允许直接依赖运行底座的地方；
- 底座缺失 / 能力缺失必须**显式降级**（capabilities 全 False / fork 降级为 replay），不得静默失败；
- 底座未公开的细节（如 patch 文件内部 schema）以 `--dump-config-schema` 输出为准，本模块不臆造字段。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from hal.capability_probe import load_capabilities, load_version_lock
from hal.interface import CAPABILITY_KEYS

DEFAULT_DSH_BIN = "dsh"
#: 未全局安装时的等价入口（官方 README：npx @deepseek-ai/dsh web）
NPM_DSH_ARGV = ("npx", "@deepseek-ai/dsh")

#: 官方 cli-help.md 列出的出厂 profile（docs/cli-help.md）
SHIPPED_PROFILES: tuple[str, ...] = ("web", "headless", "sdk", "sdk-minimal", "acp")

#: mcp-client serverName 约束：[A-Za-z0-9_-]{1,32}（docs/config-catalog.md StdioConfig）
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

DEFAULT_TOOL_CALL_TIMEOUT_MS = 60_000

#: 特性 → 最低底座版本（实测：0.1.5-rc.2 的 headless 只有裸 task 参数，
#: 无 --json / --session-id；launcher 亦无 --dump-config-schema——三者均为 0.2.x 引入）。
#: 底座处于 developer preview，官方明示会有破坏性变更，故运行期必须按版本门控。
VERSION_FEATURE_MIN: dict[str, tuple[int, int, int]] = {
    "patch_overlay": (0, 1, 0),       # --patch <path>（0.1.5-rc.2 实测存在）
    "json_events": (0, 2, 0),         # headless --json（NDJSON 事件流）
    "session_adopt": (0, 2, 0),       # headless --session-id <id>
    "config_schema_dump": (0, 2, 0),  # --dump-config-schema
}


class HarnessUnavailableError(RuntimeError):
    """底座不可用（未安装 / 版本不兼容 / 会话启动失败）。"""


@dataclass
class SessionHandle:
    """会话句柄。events 为 NDJSON 运行事件流（`headless --json`）或降级留痕。"""

    session_id: str
    preset: str
    workspace: Path
    events: list[dict] = field(default_factory=list)
    degraded: bool = False


@dataclass
class ToolSpec:
    """工具注册规格。"""

    name: str
    description: str
    input_schema: dict
    output_schema: dict


@dataclass
class PresetPatch:
    """Preset 补丁（对应 DSH 的 `--patch <path>` 叠加层）。

    `scope` 为学科/来源标识，仅用于叠加层文件名隔离——多个 Bundle 共用同一
    preset 名（默认都注入 `verity-research`）时不会互相覆盖。
    """

    preset: str
    system_prompt: str = ""
    tool_whitelist: list[str] = field(default_factory=list)
    path: Path | None = None  # 物化后的 patch 文件路径
    scope: str = ""


@dataclass
class SubagentSpec:
    """子代理规格（对应 DSH `ctx.subagents`；会话内委派走 tool-subagent）。"""

    role: str
    task: str
    permission: str = "read"
    max_context_tokens: int = 2000


def model_tool_name(server_name: str, raw_tool: str) -> str:
    """DSH 暴露给模型的 MCP 工具名：mcp__<serverName>__<rawName>。"""
    if not SERVER_NAME_RE.match(server_name):
        raise ValueError(f"非法 serverName {server_name!r}（须匹配 [A-Za-z0-9_-]{{1,32}}）")
    return f"mcp__{server_name}__{raw_tool}"


def parse_version(raw: str) -> tuple[int, int, int]:
    """解析底座版本号；无法解析时返回 (0, 0, 0)（视为不满足任何版本门控）。"""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", raw or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)


class DSHAdapter:
    """DeepSeek Harness 适配实现（经 `dsh` CLI 子进程交互）。

    `dsh_bin` 可传单可执行名（默认 `dsh`）或命令前缀
    （如 `("npx", "@deepseek-ai/dsh")`），后者用于未全局安装的环境。
    """

    def __init__(
        self,
        dsh_bin: str | tuple[str, ...] = DEFAULT_DSH_BIN,
        version_lock: Path | None = None,
        timeout: float = 600.0,
    ):
        self.argv_prefix = (dsh_bin,) if isinstance(dsh_bin, str) else tuple(dsh_bin)
        self.dsh_bin = self.argv_prefix[0]  # 可执行名（用于 which 探测）
        self.version_lock_path = version_lock or (Path(__file__).parent / "version_lock.yml")
        self.timeout = timeout
        self._sessions: dict[str, SessionHandle] = {}
        self._pending_patches: list[Path] = []
        self._installed_version: str | None = None
        self._features: dict[str, bool] | None = None

    # ── 内部工具 ──────────────────────────────────────────────────────

    def available(self) -> bool:
        """底座可执行文件是否在 PATH 上（不触发子进程）。"""
        return shutil.which(self.dsh_bin) is not None

    def resolved_bin(self) -> str:
        """解析真实可执行路径。

        Windows 上 npm 装的是 `dsh.cmd` shim，而 `shutil.which("dsh")` 的返回值
        必须直接交给 CreateProcess——裸名 `dsh`（无扩展名的 sh 脚本）会 WinError 2。
        """
        return shutil.which(self.dsh_bin) or self.dsh_bin

    def _run(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
        if not self.available():
            raise HarnessUnavailableError(f"未检测到底座可执行文件: {self.dsh_bin}")
        exe, prefix = self.resolved_bin(), self.argv_prefix[1:]
        return subprocess.run(
            [exe, *prefix, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            # Windows 上 npm shim（dsh.cmd）按本地代码页输出，非 UTF-8 时不得让
            # 适配器整体崩掉——降级信息比编码正确性更重要。
            errors="replace",
            cwd=str(cwd) if cwd else None,
            timeout=self.timeout,
        )

    def installed_version(self) -> str:
        """读取底座版本（`dsh --version`）；不可用时抛 HarnessUnavailableError。"""
        if self._installed_version is None:
            proc = self._run(["--version"])
            if proc.returncode != 0:
                raise HarnessUnavailableError(
                    (proc.stderr or "").strip() or "dsh --version 失败"
                )
            self._installed_version = (proc.stdout or "").strip()
        return self._installed_version

    def features(self) -> dict[str, bool]:
        """按运行期版本判定特性可用性（底座不可用时全部 False）。"""
        if self._features is None:
            if not self.available():
                self._features = {k: False for k in VERSION_FEATURE_MIN}
            else:
                try:
                    ver = parse_version(self.installed_version())
                except HarnessUnavailableError:
                    ver = (0, 0, 0)
                self._features = {k: ver >= minimum for k, minimum in VERSION_FEATURE_MIN.items()}
        return self._features

    def locked_version(self) -> str:
        """版本锁中已验证的底座版本。"""
        return str(load_version_lock(self.version_lock_path).get("verified_version", ""))

    def _next_session_id(self) -> str:
        return f"sess_{len(self._sessions) + 1:04d}"

    def build_run_argv(
        self,
        profile: str,
        task: str | None = None,
        *,
        session_id: str | None = None,
        json_events: bool = True,
        patch_paths: tuple[Path, ...] = (),
    ) -> list[str]:
        """构造真实 DSH 命令行（纯函数行为，便于契约测试锁定）。

        形态：`dsh --profile <profile> [--patch <p>]... [--json] [--session-id <id>] [<task>]`
        （app 参数排在 launcher 参数之后，见官方 cli-help.md 示例）。

        版本门控：`--json` / `--session-id` 为 0.2.x 引入，底座版本更低时
        **不发出**该 flag（宁可降级也不让底座因未知选项报错），降级记录见
        `start_session` 写入的 degraded 事件。
        """
        feats = self.features()
        argv = ["--profile", profile]
        for p in patch_paths:
            if feats.get("patch_overlay"):
                argv += ["--patch", str(p)]
        if json_events and feats.get("json_events"):
            argv.append("--json")
        if session_id and feats.get("session_adopt"):
            argv += ["--session-id", session_id]
        if task:
            argv.append(task)
        return argv

    def dropped_flags(self, *, json_events: bool, session_id: str | None) -> list[str]:
        """本次调用因底座版本过低而被丢弃的 flag（降级留痕用）。"""
        feats = self.features()
        dropped: list[str] = []
        if json_events and not feats.get("json_events"):
            dropped.append("--json")
        if session_id and not feats.get("session_adopt"):
            dropped.append("--session-id")
        return dropped

    @staticmethod
    def parse_event_stream(stdout: str) -> list[dict]:
        """解析 `headless --json` 的 NDJSON 事件流；非法行保留原文。"""
        events: list[dict] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                events.append({"type": "raw", "line": line})
                continue
            events.append(obj if isinstance(obj, dict) else {"type": "raw", "value": obj})
        return events

    # ── 会话生命周期 ────────────────────────────────────────────────

    def start_session(
        self,
        preset: str,
        workspace: str,
        task: str,
        session_id: str | None = None,
    ) -> SessionHandle:
        """启动一次 `headless --json` 运行；底座缺失/失败时降级为留痕句柄。"""
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)
        handle = SessionHandle(
            session_id=session_id or self._next_session_id(), preset=preset, workspace=ws
        )
        self._sessions[handle.session_id] = handle

        if not self.available():
            handle.degraded = True
            handle.events.append(
                {
                    "type": "degraded",
                    "reason": "harness_unavailable",
                    "detail": f"未检测到 {self.dsh_bin}，会话未真正启动（编排层须据此降级）",
                    "preset": preset,
                    "task": task,
                }
            )
            return handle

        argv = self.build_run_argv(
            preset, task, session_id=session_id, patch_paths=tuple(self._pending_patches)
        )
        dropped = self.dropped_flags(json_events=True, session_id=session_id)
        if dropped:
            handle.degraded = True
            handle.events.append(
                {
                    "type": "degraded",
                    "reason": "unsupported_flag",
                    "detail": (
                        f"底座版本 {self.installed_version()} 不支持 {', '.join(dropped)}"
                        "（0.2.x 引入），已降级为最终消息流"
                    ),
                    "dropped": dropped,
                }
            )
        try:
            proc = self._run(argv, cwd=ws)
        except subprocess.TimeoutExpired:
            handle.degraded = True
            handle.events.append({"type": "degraded", "reason": "timeout", "argv": argv})
            return handle

        if proc.returncode != 0:
            handle.degraded = True
            handle.events.append(
                {
                    "type": "degraded",
                    "reason": "run_failed",
                    "exit_code": proc.returncode,
                    "stderr": (proc.stderr or "").strip()[:2000],
                    "argv": argv,
                }
            )
            return handle

        handle.events.extend(self.parse_event_stream(proc.stdout))
        return handle

    def resume_session(self, handle: SessionHandle) -> SessionHandle:
        """恢复会话：真实实现为 `--session-id <id>` 接管已持久化 Session。"""
        if handle.session_id not in self._sessions:
            self._sessions[handle.session_id] = handle
        handle.events.append({"type": "session_resume", "session_id": handle.session_id})
        return handle

    def stop_session(self, handle: SessionHandle, graceful: bool = True) -> None:
        handle.events.append({"type": "session_stop", "graceful": graceful})
        if not graceful:
            self._sessions.pop(handle.session_id, None)

    # ── 轨迹与可追溯性 ──────────────────────────────────────────────

    def export_session_log(self, handle: SessionHandle):
        return iter(list(handle.events))

    def fork_trajectory(self, handle: SessionHandle, at_event: str):
        """分叉轨迹：launcher CLI 未暴露该能力，恒定降级为从事件点重放。

        DSH 会话内确有"已完成前缀分叉"（ctx.subagents 的 forkProvider /
        subagent-fork-in-process），但那是 tool-subagent 的会话内委派，
        不属于 launcher CLI 表面，HAL 不穿透（保持降级口径）。
        """
        return self.replay_to(handle, at_event)

    def replay_to(self, handle: SessionHandle, event_id: str):
        replay = SessionHandle(
            session_id=self._next_session_id(),
            preset=handle.preset,
            workspace=handle.workspace,
            events=[e for e in handle.events if e.get("id") != event_id],
        )
        replay.events.append({"type": "replay_to", "event_id": event_id})
        self._sessions[replay.session_id] = replay
        return replay

    # ── Skill / 工具注册 ───────────────────────────────────────────

    def register_skills(self, skill_dirs: list[str]) -> list[Path]:
        """发现 Skill 清单（`skills/**/SKILL.md`）。

        注入由 DSH 侧 `ctx.skills` / skill-filesystem 在会话工作目录内完成；
        HAL 只负责发现与登记，保证"Bundle 声明 = 可枚举文件"。
        """
        found: list[Path] = []
        for d in skill_dirs:
            p = Path(d)
            for skill in sorted(p.glob("**/SKILL.md")):
                found.append(skill)
        return found

    def register_tools(self, tools: list[ToolSpec]) -> list[ToolSpec]:
        for t in tools:
            for key in ("name", "description", "input_schema", "output_schema"):
                if not getattr(t, key, None):
                    raise ValueError(f"工具 {t.name} 缺少字段: {key}")
        return list(tools)

    def declare_mcp_servers(self, config: dict) -> dict:
        """校验并规范化 MCP 声明（DSH mcp-client StdioConfig 真实键）。"""
        if not config:
            return {"servers": []}
        servers = config.get("servers")
        if not isinstance(servers, list) or not servers:
            raise ValueError("mcp.servers 必须为非空列表")

        normalized: list[dict] = []
        for i, srv in enumerate(servers):
            if not isinstance(srv, dict):
                raise ValueError(f"mcp.servers[{i}] 必须为映射")
            transport = srv.get("transport", "stdio")
            if transport != "stdio":
                raise ValueError(
                    f"mcp.servers[{i}].transport={transport!r} 尚未验证"
                    "（HAL 仅锁定 stdio；HTTP 变体见官方 config-catalog）"
                )
            name = srv.get("serverName") or ""
            if not SERVER_NAME_RE.match(name):
                raise ValueError(
                    f"mcp.servers[{i}].serverName={name!r} 非法"
                    "（须匹配 [A-Za-z0-9_-]{1,32}）"
                )
            command = srv.get("command")
            if not isinstance(command, str) or not command:
                raise ValueError(f"mcp.servers[{i}].command 必须为非空字符串")
            args = srv.get("args", [])
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                raise ValueError(f"mcp.servers[{i}].args 必须为字符串列表")
            entry = {
                "transport": "stdio",
                "serverName": name,
                "command": command,
                "args": list(args),
                "toolCallTimeoutMs": int(
                    srv.get("toolCallTimeoutMs", DEFAULT_TOOL_CALL_TIMEOUT_MS)
                ),
                "failOnStartupError": bool(srv.get("failOnStartupError", True)),
            }
            if srv.get("env"):
                entry["env"] = dict(srv["env"])
            if srv.get("cwd"):
                entry["cwd"] = str(srv["cwd"])
            normalized.append(entry)
        return {"servers": normalized}

    # ── 权限与 Preset ────────────────────────────────────────────────

    def apply_preset_patch(self, patch: PresetPatch) -> PresetPatch:
        """登记 Preset 补丁；物化后以 `--patch <path>` 叠加到 profile 之上。

        patch 文件的内部 schema 以 `dsh --profile <name> --dump-config-schema`
        输出为准（DSH 0.2.x 文档未公开 patch 文件结构），故本方法只做登记与
        物化，不臆造 DSH 配置键。
        """
        if not patch.preset:
            raise ValueError("PresetPatch.preset 不能为空")
        if patch.path is None:
            out_dir = self.version_lock_path.parent / "patches"
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = f"{patch.scope}-{patch.preset}" if patch.scope else patch.preset
            path = out_dir / f"{stem}.yml"
            payload = {
                "preset": patch.preset,
                "system_prompt": patch.system_prompt,
                "tool_whitelist": list(patch.tool_whitelist),
                "_note": (
                    "verity-lens Preset Patch 叠加层；"
                    "DSH 可接受字段以 `dsh --profile <name> --dump-config-schema` 为准"
                ),
            }
            path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            patch.path = path
        self._pending_patches.append(patch.path)
        return patch

    def set_permission(self, scope: str, level: str) -> None:
        """权限级别（对应 DSH sandboxPolicy 模式：read-only / workspace-write）。"""
        if level not in ("read", "workspace_write", "none"):
            raise ValueError(f"非法权限级别: {level}")

    # ── 子代理 ────────────────────────────────────────────────────────

    def spawn_subagent(self, spec: SubagentSpec) -> SessionHandle:
        """登记子代理委派。

        DSH 侧真实委派由 `ctx.subagents`（tool-subagent / agent-team）在会话内完成，
        后端可选 subagent-spawn-in-process / subagent-fork-in-process / subagent-acp /
        subagent-dsh-sdk；launcher CLI 不直接暴露 spawn 命令，故 HAL 只登记不代跑。
        """
        handle = SessionHandle(
            session_id=self._next_session_id(),
            preset=f"subagent:{spec.role}",
            workspace=Path("."),
            degraded=True,
        )
        handle.events.append(
            {
                "type": "subagent_spawn",
                "role": spec.role,
                "permission": spec.permission,
                "detail": "由 DSH ctx.subagents 在会话内委派，launcher CLI 不代跑",
            }
        )
        self._sessions[handle.session_id] = handle
        return handle

    # ── 能力探测 ──────────────────────────────────────────────────────

    def capabilities(self) -> dict:
        """能力集 = 版本锁结论 ∩ 运行期特性探测（运行期收窄，不放宽）。

        - 底座不可执行 → 全 False；
        - 版本锁记录"针对某版本验证过"的能力（上限）；
        - 运行期按 `dsh --version` 判定的特性（--json / --session-id 等）收窄，
          避免对着旧底座发出未知选项。
        """
        caps = {k: False for k in CAPABILITY_KEYS}
        if not self.available():
            return caps
        locked = load_capabilities(self.version_lock_path)
        feats = self.features()
        for key in CAPABILITY_KEYS:
            caps[key] = bool(locked.get(key, False))
        if caps["preset_patch"] and not feats.get("patch_overlay"):
            caps["preset_patch"] = False
        if caps["session_log_export"] and not feats.get("json_events"):
            caps["session_log_export"] = False
        return caps

    def dump_config_schema(self, profile: str = "headless") -> dict | None:
        """抓取 DSH 配置 schema（`--dump-config-schema`，0.2.x 特性）。

        底座不可用 / 特性缺失 / 非零退出 / 非法 JSON → 返回 None（绝不抛错）。
        返回的 schema 为 Cordis 风格（root 为 array，含 `$defs`），非扁平 properties，
        故本方法只负责抓取，字段语义校验交给 `orchestrator/patch_schema`。
        """
        if not self.available() or not self.features().get("config_schema_dump"):
            return None
        try:
            proc = self._run(["--profile", profile, "--dump-config-schema"])
        except (HarnessUnavailableError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None

# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 状态栏：读 stdin JSON，渲染三行。

第一行：模型 / 上下文窗口。
第二行：目录 / Git 状态 / 代码量。
第三行：TTFT / TPOT / TPS / 缓存命中。

主路径只做四件事：解析 stdin、跑一次 git、读一次 transcript 尾部、拼字符串，
不读设置文件、不发网络请求。
"""

import json
import os
import subprocess
import sys
from datetime import datetime

GIT_TIMEOUT_SECONDS = 0.15
# 最近一次请求的 api-request 行和回复总在 transcript 末尾附近，只读尾部就够了。
TRANSCRIPT_TAIL_BYTES = 256 * 1024
CHANGED_STATUS_TAGS = ("1 ", "2 ")
NAMED_HEADS = {"(detached)", "(unknown)"}


# ------------------------------------------------------------
# 通用工具
# ------------------------------------------------------------
def as_mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def shorten(text: str, limit: int = 32) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def join_segments(*segments: str) -> str:
    return " | ".join(segment for segment in segments if segment)


# ------------------------------------------------------------
# 输入
# ------------------------------------------------------------
def read_input() -> dict:
    try:
        data = json.loads(sys.stdin.buffer.read())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------
# 第一行：模型 / 上下文窗口
# ------------------------------------------------------------
def model_line(data: dict) -> str:
    return join_segments(model_segment(data), context_segment(data))


def model_segment(data: dict) -> str:
    model = as_mapping(data.get("model"))
    effort = as_mapping(data.get("effort")).get("level") or "-"
    return f"model: {model.get('id') or 'unknown'}({effort})"


def context_segment(data: dict) -> str:
    window = as_mapping(data.get("context_window"))
    size = format_token_count(window.get("context_window_size"))
    used = as_int(window.get("used_percentage"))
    return f"window[{size}]: {used}%"


def format_token_count(value: object) -> str:
    count = as_int(value)
    if count >= 1_000_000:
        return f"{count // 1_000_000}M"
    if count >= 1_000:
        return f"{count // 1_000}K"
    return str(count)


# ------------------------------------------------------------
# 第二行：目录 / Git 状态 / 代码量
# ------------------------------------------------------------
def workspace_line(data: dict) -> str:
    cwd = current_dir(data)
    return join_segments(dir_segment(cwd), git_segment(cwd), code_segment(data))


def current_dir(data: dict) -> str:
    workspace = as_mapping(data.get("workspace"))
    return (
        workspace.get("current_dir")
        or data.get("cwd")
        or workspace.get("project_dir")
        or ""
    )


def dir_segment(cwd: str) -> str:
    name = os.path.basename(cwd.rstrip("/\\"))
    return f"dir: {name}" if name else ""


def code_segment(data: dict) -> str:
    cost = as_mapping(data.get("cost"))
    added = as_int(cost.get("total_lines_added"))
    removed = as_int(cost.get("total_lines_removed"))
    return f"code:+{added}/-{removed}"


# ------------------------------------------------------------
# Transcript 读取
# ------------------------------------------------------------
def read_transcript_tail(path: object) -> list[bytes]:
    if not isinstance(path, str) or not path:
        return []
    try:
        with open(path, "rb") as file:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(max(size - TRANSCRIPT_TAIL_BYTES, 0))
            raw = file.read()
    except OSError:
        return []
    if size > TRANSCRIPT_TAIL_BYTES:
        _, _, raw = raw.partition(b"\n")  # 首行多半被截断
    return raw.splitlines()


def parse_record(line: bytes) -> dict | None:
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ------------------------------------------------------------
# 第三行：TTFT / TPOT / TPS / 缓存命中
# ------------------------------------------------------------
class RequestSpeed:
    """一次请求的耗时拆分。时间戳都来自 transcript 落盘时刻，不是精确的流式时间。"""

    __slots__ = ("output_tokens", "total_seconds", "ttft_seconds")

    def __init__(
        self, ttft_seconds: float, total_seconds: float, output_tokens: int
    ) -> None:
        self.ttft_seconds = ttft_seconds
        self.total_seconds = total_seconds
        self.output_tokens = output_tokens


def speed_line(data: dict) -> str:
    speed = latest_request_speed(data)
    return join_segments(
        ttft_segment(speed),
        tpot_segment(speed),
        tps_segment(speed),
        cache_segment(data),
    )


def latest_request_speed(data: dict) -> RequestSpeed | None:
    """从 transcript 尾部倒扫最近一次有回复的主线程请求。

    状态栏输入不带耗时字段，只能估算：
    - TTFT = 首个内容块落盘时间 - 请求发出时间（含 thinking 耗时）
    - TPS  = 输出 token 数 / 整段请求耗时
    """
    replies: list[dict] = []
    for line in reversed(read_transcript_tail(data.get("transcript_path"))):
        record = parse_record(line)
        if record is None or record.get("isSidechain"):
            continue
        if record.get("type") == "assistant":
            replies.append(record)
        elif record.get("type") == "api-request":
            speed = request_speed(record, replies)
            if speed:
                return speed
    return None


def request_speed(request: dict, replies: list[dict]) -> RequestSpeed | None:
    started_at = parse_timestamp(request.get("timestamp"))
    matched = [
        reply for reply in replies if reply.get("requestRef") == request.get("id")
    ]
    reply_times = [
        moment
        for moment in (parse_timestamp(reply.get("timestamp")) for reply in matched)
        if moment
    ]
    tokens = max((reply_output_tokens(reply) for reply in matched), default=0)
    if started_at is None or not reply_times or tokens <= 0:
        return None

    first_at, last_at = min(reply_times), max(reply_times)
    return RequestSpeed(
        (first_at - started_at).total_seconds(),
        (last_at - started_at).total_seconds(),
        tokens,
    )


def reply_output_tokens(reply: dict) -> int:
    usage = as_mapping(as_mapping(reply.get("message")).get("usage"))
    return as_int(usage.get("output_tokens"))


def format_seconds(seconds: float) -> str:
    return f"{seconds:.1f}s" if seconds >= 1 else f"{seconds * 1000:.0f}ms"


def ttft_segment(speed: RequestSpeed | None) -> str:
    if not speed:
        return "ttft: -"
    return f"ttft: {format_seconds(speed.ttft_seconds)}"


def tpot_segment(speed: RequestSpeed | None) -> str:
    if not speed or speed.total_seconds <= 0:
        return "tpot: -"
    return f"tpot: {speed.total_seconds / speed.output_tokens * 1000:.1f}ms"


def tps_segment(speed: RequestSpeed | None) -> str:
    if not speed or speed.total_seconds <= 0:
        return "tps: -"
    return f"tps: {speed.output_tokens / speed.total_seconds:.0f}"


def cache_segment(data: dict) -> str:
    ratio = as_mapping(data.get("prompt_cache")).get("hit_ratio")
    if not isinstance(ratio, (int, float)):
        percent = 0
    elif ratio <= 1:  # 接口可能给 0~1 的小数，也可能直接给百分数
        percent = round(ratio * 100)
    else:
        percent = round(ratio)
    return f"cache: {percent}%"


# ------------------------------------------------------------
# Git 状态
# ------------------------------------------------------------
class GitStatus:
    """git status --porcelain=v2 的解析结果。"""

    __slots__ = (
        "ahead",
        "behind",
        "conflicts",
        "deleted",
        "has_ahead_behind",
        "head",
        "modified",
        "oid",
        "staged",
        "untracked",
        "upstream",
    )

    def __init__(self) -> None:
        self.head = self.oid = self.upstream = ""
        self.has_ahead_behind = False
        self.ahead = self.behind = 0
        self.conflicts = self.staged = self.modified = self.deleted = 0
        self.untracked = 0


def git_segment(cwd: str) -> str:
    if not cwd:
        return ""

    status = run_git_status(cwd)
    if not status:
        return ""

    state = parse_git_status(status)
    parts = [f"git:{git_ref(state)}", *sync_parts(state), *change_parts(state)]
    return join_segments(*parts)


def run_git_status(cwd: str) -> str:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                cwd,
                "status",
                "--porcelain=v2",
                "--branch",
                "--untracked-files=normal",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def parse_git_status(status: str) -> GitStatus:
    state = GitStatus()
    for line in status.splitlines():
        if line.startswith("# branch."):
            parse_branch_header(line, state)
        elif line.startswith("? "):
            state.untracked += 1
        elif line.startswith("u "):
            state.conflicts += 1
        elif line.startswith(CHANGED_STATUS_TAGS):
            count_change(line, state)
    return state


def parse_branch_header(line: str, state: GitStatus) -> None:
    key, _, value = line.removeprefix("# branch.").partition(" ")
    if key == "head":
        state.head = value
    elif key == "oid":
        state.oid = value
    elif key == "upstream":
        state.upstream = value
    elif key == "ab":
        state.has_ahead_behind = True
        for flag in value.split():
            if flag.startswith("+"):
                state.ahead = as_int(flag[1:])
            elif flag.startswith("-"):
                state.behind = as_int(flag[1:])


def count_change(line: str, state: GitStatus) -> None:
    fields = line.split(maxsplit=2)
    if len(fields) < 2:
        return
    index_status, worktree_status = fields[1][:2]
    if "D" in (index_status, worktree_status):
        state.deleted += 1
    if index_status not in ".D":
        state.staged += 1
    if worktree_status not in ".D":
        state.modified += 1


def git_ref(state: GitStatus) -> str:
    if state.head and state.head not in NAMED_HEADS:
        return shorten(state.head)
    if state.oid and state.oid != "(initial)":
        return f"@{state.oid[:7]}"
    return "unknown"


def sync_parts(state: GitStatus) -> list[str]:
    named_head = bool(state.head) and state.head not in NAMED_HEADS
    if not state.upstream:
        return ["no-up"] if named_head else []
    if not state.has_ahead_behind:
        return ["no-ab"]

    parts = []
    if state.ahead:
        parts.append(f"↑{state.ahead}")
    if state.behind:
        parts.append(f"↓{state.behind}")
    return parts or ["sync"]


def change_parts(state: GitStatus) -> list[str]:
    counts = (
        (state.conflicts, "!"),
        (state.staged, "+"),
        (state.modified, "~"),
        (state.deleted, "-"),
        (state.untracked, "?"),
    )
    parts = [f"{token}{count}" for count, token in counts if count]
    return parts or ["clean"]


# ------------------------------------------------------------
# 渲染与入口
# ------------------------------------------------------------
def render(data: dict) -> str:
    lines = (
        model_line(data),
        workspace_line(data),
        speed_line(data),
    )
    return "\n".join(line for line in lines if line)


def main() -> int:
    print(render(read_input()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

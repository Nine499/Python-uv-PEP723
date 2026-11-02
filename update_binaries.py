# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx[http2]>=0.27.0",
#   "tqdm>=4.66.0",
# ]
# ///
"""并发更新 ~/.local/bin 下的命令行工具。

每个工具独立执行：查询最新 release → 下载（支持 Range 时分段并发）→
只从归档中取出需要的成员 → 原子替换到目标目录。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Coroutine, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, NoReturn, Self
from urllib.parse import unquote, urlsplit

import httpx  # pyright: ignore[reportMissingImports]
from tqdm import tqdm  # pyright: ignore[reportMissingModuleSource]

BIN_DIR = Path("~/.local/bin").expanduser()
CONCURRENCY = 3
SEGMENTS = 5
MIN_SEGMENT_SIZE = 1 << 20
CHUNK_SIZE = 1 << 17
MAX_ATTEMPTS = 3
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

COLOR = {
    "INFO": "\033[94m",
    "OK": "\033[92m",
    "ERR": "\033[91m",
    "WARN": "\033[93m",
    "END": "\033[0m",
}


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    repo: str
    url: str
    files: dict[str, str]
    is_archive: bool = True


TOOLS = (
    Tool(
        "qdns",
        "natesales/q",
        "https://github.com/natesales/q/releases/download/v{ver}/q_{ver}_linux_amd64.tar.gz",
        {"q": "qdns"},
    ),
    Tool(
        "fzf",
        "junegunn/fzf",
        "https://github.com/junegunn/fzf/releases/download/v{ver}/fzf-{ver}-linux_amd64.tar.gz",
        {"fzf": "fzf"},
    ),
    Tool(
        "yazi",
        "sxyazi/yazi",
        "https://github.com/sxyazi/yazi/releases/download/v{ver}/yazi-x86_64-unknown-linux-gnu.zip",
        {"yazi": "yazi", "ya": "ya"},
    ),
    Tool(
        "starship",
        "starship/starship",
        "https://github.com/starship/starship/releases/download/v{ver}/starship-x86_64-unknown-linux-gnu.tar.gz",
        {"starship": "starship"},
    ),
    Tool(
        "lazygit",
        "jesseduffield/lazygit",
        "https://github.com/jesseduffield/lazygit/releases/download/v{ver}/lazygit_{ver}_linux_x86_64.tar.gz",
        {"lazygit": "lazygit"},
    ),
    Tool(
        "zoxide",
        "ajeetdsouza/zoxide",
        "https://github.com/ajeetdsouza/zoxide/releases/download/v{ver}/zoxide-{ver}-x86_64-unknown-linux-musl.tar.gz",
        {"zoxide": "zoxide"},
    ),
    Tool(
        "yq",
        "mikefarah/yq",
        "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64",
        {"yq_linux_amd64": "yq"},
        False,
    ),
    Tool(
        "yt-dlp",
        "yt-dlp/yt-dlp",
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp",
        {"yt-dlp": "yt-dlp"},
        False,
    ),
    Tool(
        "tcping",
        "nodeseeker/tcping",
        "https://github.com/nodeseeker/tcping/releases/download/v{ver}/tcping-linux-amd64.zip",
        {"tcping": "tcping"},
    ),
    Tool(
        "herdr",
        "herdrdev/herdr",
        "https://github.com/herdrdev/herdr/releases/download/v{ver}/herdr-linux-x86_64",
        {"herdr-linux-x86_64": "herdr"},
        False,
    ),
)


class UpdateError(Exception):
    """可预期的更新失败，消息直接展示给用户。"""


class RetryableError(UpdateError):
    """值得重试的失败：网络中断、限流、响应截断等。"""


def log(message: str, level: str = "INFO") -> None:
    tqdm.write(f"{COLOR[level]}{message}{COLOR['END']}")


async def backoff(attempt: int, reason: object) -> None:
    wait = 2**attempt
    log(f"  {reason}，{wait}s 后重试", "WARN")
    await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# 网络请求
# ---------------------------------------------------------------------------


def github_token() -> str | None:
    """优先读 $SECRETS49/.env 的 github-no-403，退回 GITHUB_TOKEN。

    未认证的 api.github.com 每小时只有 60 次额度，超限即 403。
    """
    secrets = os.environ.get("SECRETS49")
    if secrets:
        try:
            lines = (Path(secrets) / ".env").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            key, sep, value = line.partition("=")
            if sep and key.strip() == "github-no-403":
                return value.strip().strip("'\"") or None
    return os.environ.get("GITHUB_TOKEN") or None


def api_headers() -> dict[str, str]:
    """只给 api.github.com 带 token，避免泄露给下载域名。"""
    headers = {"Accept": "application/vnd.github+json"}
    if token := github_token():
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    """GET 小响应；网络错误与可重试状态码按指数退避重试。"""
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.get(url, headers=headers)
        except httpx.TransportError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise UpdateError(f"请求失败: {exc}") from exc
            await backoff(attempt, exc)
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS - 1:
            status = response.status_code
            await response.aclose()
            await backoff(attempt, f"HTTP {status}")
            continue
        return response

    raise AssertionError("unreachable")


async def latest_version(client: httpx.AsyncClient, repo: str) -> str:
    response = await fetch(
        client,
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers=api_headers(),
    )
    response.raise_for_status()
    try:
        tag = response.json()["tag_name"]
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError(f"{repo} 的 release 响应缺少 tag_name") from exc
    if not isinstance(tag, str) or not tag:
        raise UpdateError(f"{repo} 的 tag_name 无效: {tag!r}")
    return tag.removeprefix("v")


def filename_from_url(url: str) -> str:
    return unquote(PurePosixPath(urlsplit(url).path).name) or "download"


def content_length(headers: httpx.Headers) -> int | None:
    value = headers.get("content-length")
    return int(value) if value and value.isdigit() else None


def content_range_total(value: str | None) -> int | None:
    if not value:
        return None
    _, _, total = value.rpartition("/")
    return int(total) if total.isdigit() else None


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


class SegmentFile:
    """按偏移并发写入固定长度的文件。"""

    def __init__(self, path: Path, size: int) -> None:
        self._path = path
        self._size = size
        self._fd = -1

    def __enter__(self) -> Self:
        self._fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.ftruncate(self._fd, self._size)
        return self

    def __exit__(self, *exc_info: object) -> None:
        os.close(self._fd)

    def write(self, offset: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.pwrite(self._fd, view, offset)
            offset += written
            view = view[written:]


class _Segment:
    """表示文件的一段字节闭区间。"""

    __slots__ = ("end", "start")

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end


def plan_segments(total: int) -> list[_Segment]:
    count = min(SEGMENTS, max(1, total // MIN_SEGMENT_SIZE))
    step = -(-total // count)
    return [
        _Segment(start, min(start + step, total) - 1) for start in range(0, total, step)
    ]


def progress_bar(label: str, total: int | None) -> tqdm:
    """软件名与版本写进同一条进度条，原地刷新。"""
    return tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        colour="blue",
        desc=label,
        leave=False,
        bar_format="{desc}, {percentage:3.0f}%|{bar}{r_bar}",
    )


async def download(
    client: httpx.AsyncClient, url: str, target: Path, label: str
) -> None:
    """下载 url 到 target；支持 Range 时并发分段。"""
    for attempt in range(MAX_ATTEMPTS):
        try:
            await download_once(client, url, target, label)
            return
        except (httpx.TransportError, RetryableError) as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise UpdateError(f"下载失败: {url}（{exc}）") from exc
            await backoff(attempt, exc)


async def download_once(
    client: httpx.AsyncClient, url: str, target: Path, label: str
) -> None:
    # 用 1 字节的 Range 探测：206 表示支持分段，200 表示响应体就是整个文件。
    headers = {"Range": "bytes=0-0", "Accept-Encoding": "identity"}
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 200:
            total = content_length(response.headers)
            with (
                progress_bar(label, total) as bar,
                target.open("wb") as file,
            ):
                await consume(response, file, bar)
            return
        if response.status_code != 206:
            raise_status(response)
        total = content_range_total(response.headers.get("content-range"))

    if total is None or total < 2 * MIN_SEGMENT_SIZE:
        await stream_to_file(client, url, target, label)
        return
    await segmented_download(client, url, target, total, label)


async def stream_to_file(
    client: httpx.AsyncClient, url: str, target: Path, label: str
) -> None:
    async with client.stream(
        "GET", url, headers={"Accept-Encoding": "identity"}
    ) as response:
        if response.status_code != 200:
            raise_status(response)
        total = content_length(response.headers)
        with (
            progress_bar(label, total) as bar,
            target.open("wb") as file,
        ):
            await consume(response, file, bar)


async def consume(response: httpx.Response, file: BinaryIO, bar: tqdm) -> None:
    async for chunk in response.aiter_raw(CHUNK_SIZE):
        file.write(chunk)
        bar.update(len(chunk))


async def segmented_download(
    client: httpx.AsyncClient, url: str, target: Path, total: int, label: str
) -> None:
    segments = plan_segments(total)
    with (
        progress_bar(label, total) as bar,
        SegmentFile(target, total) as writer,
    ):
        await gather_all(
            fetch_segment(client, url, writer, segment, bar) for segment in segments
        )


async def fetch_segment(
    client: httpx.AsyncClient,
    url: str,
    writer: SegmentFile,
    segment: _Segment,
    bar: tqdm,
) -> None:
    headers = {
        "Range": f"bytes={segment.start}-{segment.end}",
        "Accept-Encoding": "identity",
    }
    async with client.stream("GET", url, headers=headers) as response:
        if response.status_code != 206:
            raise_status(response)
        position = segment.start
        async for chunk in response.aiter_raw(CHUNK_SIZE):
            writer.write(position, chunk)
            position += len(chunk)
            bar.update(len(chunk))
    if position != segment.end + 1:
        raise RetryableError(f"分段 {segment.start}-{segment.end} 响应被截断")


def raise_status(response: httpx.Response) -> NoReturn:
    status = response.status_code
    if status in RETRYABLE_STATUS:
        raise RetryableError(f"HTTP {status}")
    raise UpdateError(f"HTTP {status}: {response.url}")


async def gather_all(coroutines: Iterable[Coroutine[Any, Any, None]]) -> None:
    """并发执行并传播异常；任一任务失败时取消其余任务。"""
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


# ---------------------------------------------------------------------------
# 解包与安装
# ---------------------------------------------------------------------------


def extract(archive: Path, wanted: dict[str, str], workdir: Path) -> dict[str, Path]:
    """只从归档中取出 wanted 列出的成员，返回 安装名 -> 临时路径。"""
    workdir.mkdir(parents=True, exist_ok=True)
    remaining = {key.lower(): install for key, install in wanted.items()}
    if archive.suffix == ".zip":
        extract_zip(archive, remaining, workdir)
    else:
        extract_tar(archive, remaining, workdir)
    if remaining:
        raise UpdateError(f"归档中缺少: {', '.join(sorted(remaining))}")
    return {install: workdir / install for install in wanted.values()}


def extract_zip(archive: Path, remaining: dict[str, str], workdir: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            if info.is_dir():
                continue
            key = PurePosixPath(info.filename).name.lower()
            install = remaining.get(key)
            if install is None:
                continue
            with source.open(info) as member, (workdir / install).open("wb") as target:
                shutil.copyfileobj(member, target, CHUNK_SIZE)
            remaining.pop(key)
            if not remaining:
                return


def extract_tar(archive: Path, remaining: dict[str, str], workdir: Path) -> None:
    with tarfile.open(archive, "r:*") as source:
        for info in source:
            if not info.isfile():
                continue
            key = PurePosixPath(info.name).name.lower()
            install = remaining.get(key)
            if install is None:
                continue
            member = source.extractfile(info)
            if member is None:
                continue
            with member, (workdir / install).open("wb") as target:
                shutil.copyfileobj(member, target, CHUNK_SIZE)
            remaining.pop(key)
            if not remaining:
                return


def install(source: Path, name: str) -> Path:
    """复制到同目录临时文件后原子替换，避免留下写了一半的二进制。"""
    destination = BIN_DIR / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(source, staging)
        staging.chmod(0o755)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def update_tool(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, tool: Tool
) -> bool:
    async with semaphore:
        try:
            version = await latest_version(client, tool.repo)
            url = tool.url.format(ver=version)

            with tempfile.TemporaryDirectory(prefix=f"updater-{tool.name}-") as tmp:
                workdir = Path(tmp)
                download_path = workdir / filename_from_url(url)
                await download(client, url, download_path, f"{tool.name},v{version}")
                sources = (
                    extract(download_path, tool.files, workdir)
                    if tool.is_archive
                    else {
                        install_name: download_path
                        for install_name in tool.files.values()
                    }
                )
                installed = [install(source, name) for name, source in sources.items()]

            log(f"  ✓ {', '.join(map(str, installed))}", "OK")
            return True
        except (
            UpdateError,
            httpx.HTTPError,
            OSError,
            tarfile.TarError,
            zipfile.BadZipFile,
        ) as exc:
            log(f"  {tool.name} ✗ {type(exc).__name__}: {exc}", "ERR")
            return False


async def run() -> int:
    log("Geek Updater Started")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(
        max_connections=CONCURRENCY * SEGMENTS,
        max_keepalive_connections=CONCURRENCY * SEGMENTS,
    )
    async with httpx.AsyncClient(
        http2=True,
        headers={"User-Agent": "GeekUpdater/4.0"},
        timeout=TIMEOUT,
        follow_redirects=True,
        limits=limits,
    ) as client:
        results = await asyncio.gather(
            *(update_tool(client, semaphore, tool) for tool in TOOLS)
        )

    ok = sum(results)
    log(
        f"\nResult: {ok}/{len(TOOLS)} updated",
        "OK" if ok == len(TOOLS) else "ERR",
    )
    return 0 if ok == len(TOOLS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

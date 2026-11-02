# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx>=0.27.0",
# ]
# ///
"""上传一张图片到 imgchest，把返回的直链打印到标准输出。

用法: uv run imgchest_upload.py <图片文件>
"""

import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]

API_URL = "https://api.imgchest.com/v1/post"
API_KEY_ENV_NAMES = ("IMGCHEST_API_KEY", "imgchest-key")
FORM_FIELDS = {"privacy": "hidden", "anonymous": "1", "nsfw": "1"}
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_ATTEMPTS = 3
RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

EXIT_USAGE = 1  # 参数、文件或配置错误
EXIT_RESPONSE = 2  # HTTP 状态码异常，或响应内容不符合预期
EXIT_NETWORK = 3  # 网络错误，重试耗尽


class UploadError(Exception):
    """可预期的失败：消息直接展示给用户，exit_code 作为进程退出码。"""

    def __init__(self, message: str, exit_code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def parse_env(text: str) -> dict[str, str]:
    """解析 .env 文本；忽略空行与注释，支持 export 前缀和引号包裹的值。"""
    pairs: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.removeprefix("export ").partition("=")
        if separator and name.strip():
            pairs[name.strip()] = value.strip().strip("\"'")
    return pairs


def read_api_key() -> str:
    """读取 $SECRETS49/.env 中的图床 API key。"""
    secrets_dir = os.environ.get("SECRETS49")
    if not secrets_dir:
        raise UploadError("配置错误: 未设置环境变量 SECRETS49")

    env_path = Path(secrets_dir) / ".env"
    try:
        env = parse_env(env_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UploadError(f"配置错误: 无法读取 {env_path}: {exc}") from exc

    for name in API_KEY_ENV_NAMES:
        if api_key := env.get(name):
            return api_key

    names = " / ".join(API_KEY_ENV_NAMES)
    raise UploadError(f"配置错误: {env_path} 中没有非空的 API key（候选键名: {names}）")


# ---------------------------------------------------------------------------
# 上传
# ---------------------------------------------------------------------------


class Uploader:
    def __init__(self, client: httpx.Client, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    def upload(self, file_path: Path) -> list[str]:
        return extract_links(self._post_with_retry(file_path))

    def _post_with_retry(self, file_path: Path) -> httpx.Response:
        """网络错误或可重试状态码按指数退避重试，返回最后一次响应。"""
        last_error: httpx.TransportError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._post(file_path)
            except httpx.TransportError as exc:
                last_error = exc
                problem = f"网络错误: {exc}"
            except OSError as exc:
                raise UploadError(
                    f"本地文件错误: 读取 {file_path} 失败: {exc}"
                ) from exc
            else:
                if (
                    response.status_code not in RETRYABLE_STATUSES
                    or attempt == MAX_ATTEMPTS
                ):
                    return response
                problem = f"HTTP {response.status_code}"
                response.close()

            wait = 2 ** (attempt - 1)
            print(
                f"{problem}，{wait} 秒后重试（{attempt}/{MAX_ATTEMPTS}）",
                file=sys.stderr,
            )
            time.sleep(wait)

        # 可重试状态码在最后一次尝试时直接返回，这里只可能是网络错误耗尽
        raise UploadError(
            f"网络错误: 尝试 {MAX_ATTEMPTS} 次后仍失败: {last_error}", EXIT_NETWORK
        ) from last_error

    def _post(self, file_path: Path) -> httpx.Response:
        mime_type = (
            mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        )
        try:
            image = file_path.open("rb")
        except OSError as exc:
            raise UploadError(f"本地文件错误: 无法打开 {file_path}: {exc}") from exc

        with image:
            return self._client.post(
                API_URL,
                data=FORM_FIELDS,
                files={"images[]": (file_path.name, image, mime_type)},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )


# ---------------------------------------------------------------------------
# 响应解析
# ---------------------------------------------------------------------------


def decode_body(response: httpx.Response) -> tuple[Any, str]:
    """返回 (解析后的 JSON, 原始文本)；不是 JSON 时解析结果为 None。"""
    text = response.text
    try:
        return json.loads(text), text
    except ValueError:
        return None, text


def pretty(body: Any, text: str) -> str:
    return json.dumps(body, ensure_ascii=False, indent=2) if body is not None else text


def extract_links(response: httpx.Response) -> list[str]:
    """校验响应并取出图片链接，不符合预期时抛 UploadError。"""
    body, text = decode_body(response)

    if not response.is_success:
        raise UploadError(
            f"HTTP {response.status_code}\n{pretty(body, text)}", EXIT_RESPONSE
        )

    try:
        links = [str(image["link"]) for image in body["data"]["images"]]
    except (KeyError, TypeError) as exc:
        raise UploadError(
            f"响应格式错误（{exc}）\n{pretty(body, text)}", EXIT_RESPONSE
        ) from exc

    if not links:
        raise UploadError("响应中没有图片链接", EXIT_RESPONSE)
    return links


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(f"用法: uv run {sys.argv[0]} <图片文件>", file=sys.stderr)
        return EXIT_USAGE

    file_path = Path(args[0])
    if not file_path.is_file():
        print(f"本地文件错误: 文件不存在或不是普通文件: {file_path}", file=sys.stderr)
        return EXIT_USAGE

    try:
        api_key = read_api_key()
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            links = Uploader(client, api_key).upload(file_path)
    except UploadError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code

    print("\n".join(links))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

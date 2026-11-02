# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""查询并打印 DeepSeek 账户余额。

余额来自 https://api.deepseek.com/user/balance，
API key 从 $SECRETS49/.env 的 deepseek-key 读取。
输出单行：DS余额：12.34

查询结果缓存在系统临时目录，5 分钟内重复运行不再请求接口。
"""

import json
import os
import sys
import tempfile
import time
import urllib.request

BALANCE_URL = "https://api.deepseek.com/user/balance"
REQUEST_TIMEOUT_SECONDS = 10

CACHE_PATH = os.path.join(tempfile.gettempdir(), "deepseek_usage_cache.json")
CACHE_TTL_SECONDS = 300

SECRETS_DIR_ENV = "SECRETS49"
API_KEY_NAME = "deepseek-key"


def read_api_key() -> str:
    """从 $SECRETS49/.env 读取 deepseek-key，缺失时退出并说明原因。"""
    secrets_dir = os.environ.get(SECRETS_DIR_ENV)
    if not secrets_dir:
        sys.exit(f"环境变量 {SECRETS_DIR_ENV} 未设置")

    env_file = os.path.join(secrets_dir, ".env")
    try:
        with open(env_file, encoding="utf-8") as file:
            lines = file.read().splitlines()
    except OSError:
        sys.exit(f"无法读取 {env_file}")

    for line in lines:
        name, separator, value = line.partition("=")
        if separator and name.strip() == API_KEY_NAME:
            return value.strip().strip("'\"")
    sys.exit(f"{env_file} 里没有 {API_KEY_NAME}")


def fetch_balance(api_key: str) -> dict:
    request = urllib.request.Request(
        BALANCE_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            return json.load(response)
    except (OSError, ValueError):
        sys.exit("查询 DeepSeek 余额失败：网络或响应异常")


def load_cached_payload() -> dict | None:
    """返回 5 分钟内的缓存响应，没有或已过期时返回 None。"""
    try:
        with open(CACHE_PATH, encoding="utf-8") as file:
            cached = json.load(file)
    except (OSError, ValueError):
        return None

    if not isinstance(cached, dict):
        return None
    fetched_at = cached.get("fetched_at")
    if not isinstance(fetched_at, (int, float)):
        return None
    if time.time() - fetched_at > CACHE_TTL_SECONDS:
        return None

    payload = cached.get("payload")
    return payload if isinstance(payload, dict) else None


def save_cached_payload(payload: dict) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as file:
            json.dump({"fetched_at": time.time(), "payload": payload}, file)
    except OSError:
        print(f"警告：无法写入缓存 {CACHE_PATH}", file=sys.stderr)


def format_balance(payload: dict) -> str:
    if payload.get("is_available") is False:
        return "DS余额：不可用"

    balance_infos = payload.get("balance_infos")
    if not isinstance(balance_infos, list):
        return ""
    infos = [item for item in balance_infos if isinstance(item, dict)]
    if not infos:
        return ""

    info = next((item for item in infos if item.get("currency") == "CNY"), infos[0])
    return f"DS余额：{format_amount(info.get('total_balance'))}"


def format_amount(value: object) -> str:
    try:
        amount = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        amount = 0.0
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def main() -> None:
    payload = load_cached_payload()
    is_cached = payload is not None
    if payload is None:
        payload = fetch_balance(read_api_key())

    text = format_balance(payload)
    if not text:
        sys.exit("响应里没有余额数据")

    if not is_cached:
        save_cached_payload(payload)
    print(text)


if __name__ == "__main__":
    main()

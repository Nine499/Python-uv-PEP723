#!/usr/bin/env python3
"""查询并打印 OpenCode Go 的剩余用量。

用量数据来自 https://opencode.ai/zen/go/v1/usage，
API key 从 $SECRETS49/.env 的 opencode-go-key 读取。
输出单行：剩余 5h:98%(9m) 7d:99%(1d12h) 1m:100%(29d)

查询结果缓存在系统临时目录，5 分钟内重复运行不再请求接口。
"""

import json
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime

USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
USER_AGENT = "opencode-usage/1.0"  # 接口会拒绝 urllib 默认 UA（403）
REQUEST_TIMEOUT_SECONDS = 30

CACHE_PATH = os.path.join(tempfile.gettempdir(), "opencode_usage_cache.json")
CACHE_TTL_SECONDS = 300

SECRETS_DIR_ENV = "SECRETS49"
API_KEY_NAME = "opencode-go-key"

# 每项配额：(展示标签, 接口字段名, 时间单位（从大到小）)
QUOTAS = (
    ("5h", "rolling", (("h", 3600), ("m", 60))),
    ("7d", "weekly", (("d", 86400), ("h", 3600))),
    ("1m", "monthly", (("d", 86400),)),
)


# ------------------------------------------------------------
# 配置与请求
# ------------------------------------------------------------
def read_api_key() -> str:
    """从 $SECRETS49/.env 读取 opencode-go-key，缺失时退出并说明原因。"""
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


def fetch_usage(api_key: str) -> dict:
    """请求用量接口，返回响应中的 usage 对象。"""
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        sys.exit("查询 OpenCode 用量失败：网络或响应异常")

    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict) or not usage:
        sys.exit("响应里没有 OpenCode 用量数据")
    return usage


# ------------------------------------------------------------
# 缓存
# ------------------------------------------------------------
def load_cached_usage() -> dict | None:
    """返回 5 分钟内的缓存用量，没有或已过期时返回 None。"""
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

    usage = cached.get("usage")
    return usage if isinstance(usage, dict) and usage else None


def save_cached_usage(usage: dict) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as file:
            json.dump({"fetched_at": time.time(), "usage": usage}, file)
    except OSError:
        print(f"警告：无法写入缓存 {CACHE_PATH}", file=sys.stderr)


# ------------------------------------------------------------
# 格式化
# ------------------------------------------------------------
def remaining_percent(quota: object) -> str:
    """把接口给的已用百分比换算成剩余百分比。"""
    if not isinstance(quota, dict):
        return "--"
    if quota.get("status") == "rate-limited":
        return "0%"

    try:
        used = float(quota["percent"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError):
        return "--"

    used = min(100.0, max(0.0, used))
    return f"{int(100 - used + 0.5)}%"


def seconds_until_reset(quota: dict) -> int | None:
    """距离 resetsAt 的剩余秒数，无法解析时返回 None。"""
    resets_at = quota.get("resetsAt")
    if not isinstance(resets_at, str):
        return None

    try:
        reset_timestamp = datetime.fromisoformat(resets_at).timestamp()
    except (TypeError, ValueError):
        return None
    return max(0, int(reset_timestamp - time.time()))


def format_time_left(quota: object, time_units: tuple[tuple[str, int], ...]) -> str:
    """按给定的时间单位格式化剩余时间，最高位为零时自动降级。"""
    if not isinstance(quota, dict):
        return "--"

    seconds = seconds_until_reset(quota)
    if seconds is None:
        return "--"

    # 跳过值为零的高位单位，例如 90 秒显示 1m 而不是 0h1m
    start = 0
    while start < len(time_units) - 1 and seconds < time_units[start][1]:
        start += 1

    parts = []
    for unit_name, unit_seconds in time_units[start:]:
        parts.append(f"{seconds // unit_seconds}{unit_name}")
        seconds %= unit_seconds
    return "".join(parts)


def format_quota(
    label: str,
    key: str,
    time_units: tuple[tuple[str, int], ...],
    usage: dict,
) -> str:
    """输出一项配额，例如 5h:98%(9m)。"""
    quota = usage.get(key)
    return f"{label}:{remaining_percent(quota)}({format_time_left(quota, time_units)})"


# ------------------------------------------------------------
# 入口
# ------------------------------------------------------------
def main() -> None:
    usage = load_cached_usage()
    if usage is None:
        usage = fetch_usage(read_api_key())
        save_cached_usage(usage)

    quotas = " ".join(
        format_quota(label, key, time_units, usage) for label, key, time_units in QUOTAS
    )
    print(f"剩余 {quotas}")


if __name__ == "__main__":
    main()

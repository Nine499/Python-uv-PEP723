# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6.0.2,<7"]
# ///
"""把 $SECRETS49/claudecode_api.yaml 中选中的配置合并进 ~/.claude/settings.json。"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml  # pyright: ignore[reportMissingImports]

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CONFIG_FILENAME = "claudecode_api.yaml"


class ConfigError(Exception):
    """可预期的配置或输入错误，消息直接展示给用户。"""


# ---------------------------------------------------------------------------
# 读取配置
# ---------------------------------------------------------------------------


def load_configs() -> dict[str, dict[str, str]]:
    secrets_dir = os.environ.get("SECRETS49")
    if not secrets_dir:
        raise ConfigError("配置错误: 未设置环境变量 SECRETS49")

    config_path = Path(secrets_dir) / CONFIG_FILENAME
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"配置错误: 无法读取 {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置错误: {config_path} 不是合法 YAML: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise ConfigError(f"配置错误: {config_path} 必须是非空映射")

    return {str(name): string_map(name, values) for name, values in raw.items()}


def string_map(name: str, values: object) -> dict[str, str]:
    if not isinstance(values, dict):
        raise ConfigError(f"配置错误: {name!r} 必须是键值映射")

    result: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ConfigError(f"配置错误: {name!r} 的 {key!r} 必须是字符串")
        result[key] = value
    return result


def choose_config(configs: dict[str, dict[str, str]]) -> tuple[str, dict[str, str]]:
    names = list(configs)
    print("可用配置：")
    for index, name in enumerate(names, start=1):
        print(f"  {index}. {name}")

    while True:
        try:
            choice = input("请选择配置编号：").strip()
        except EOFError as exc:
            raise ConfigError("输入错误: 没有读到选择") from exc

        if choice.isdigit() and 1 <= (number := int(choice)) <= len(names):
            name = names[number - 1]
            return name, configs[name]
        print(f"请输入 1 到 {len(names)} 之间的整数。", file=sys.stderr)


# ---------------------------------------------------------------------------
# 写入 settings
# ---------------------------------------------------------------------------


def read_settings(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"配置错误: 无法读取 {path}: {exc}") from exc

    try:
        settings = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"配置错误: {path} 不是合法 JSON: {exc}") from exc

    if not isinstance(settings, dict):
        raise ConfigError(f"配置错误: {path} 的根节点必须是对象")
    return settings


def merge_env(settings: dict[str, Any], config: dict[str, str]) -> dict[str, Any]:
    env = settings.get("env", {})
    if not isinstance(env, dict):
        raise ConfigError("配置错误: settings.json 的 env 必须是对象")
    return {**settings, "env": {**env, **config}}


def write_if_changed(path: Path, settings: dict[str, Any]) -> bool:
    """内容有变化才写入，并用临时文件原子替换。"""
    text = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"

    try:
        if path.read_text(encoding="utf-8") == text:
            return False
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    except OSError as exc:
        raise ConfigError(f"配置错误: 无法读取 {path}: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        staging.write_text(text, encoding="utf-8")
        staging.chmod(mode)
        os.replace(staging, path)
    except OSError as exc:
        raise ConfigError(f"配置错误: 无法写入 {path}: {exc}") from exc
    finally:
        staging.unlink(missing_ok=True)
    return True


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> int:
    try:
        configs = load_configs()
        name, config = choose_config(configs)
        settings = merge_env(read_settings(SETTINGS_PATH), config)
        changed = write_if_changed(SETTINGS_PATH, settings)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130

    action = "已更新" if changed else "无变化"
    print(f"{action}: 配置 {name!r} 已合并到 {SETTINGS_PATH} 的 env。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

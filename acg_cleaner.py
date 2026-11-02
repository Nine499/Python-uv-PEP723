# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""批量清理目标文件夹：删 GIF、批量重命名、删非 WebP、删空文件夹。

运行：uv run acg_cleaner.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

TARGET = Path("/mnt/c/Users/Forty/acg/1")
GIF_SUFFIX = ".gif"
WEBP_SUFFIX = ".webp"
NUMBER_WIDTH = 7

MENU = """
========== ACG 清理工具 ==========
目标文件夹：{target}
  1. 删除所有 GIF 文件（含子文件夹）
  2. 把所有文件重命名为 0000001 递增序号（保留扩展名）
  3. 删除所有非 WebP 文件（需三次确认）
  4. 删除所有空文件夹
  0. 退出
=================================="""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(TARGET))
    except ValueError:
        return str(path)


def collect_files(root: Path) -> list[Path]:
    """返回 root 下所有文件的路径（含隐藏文件和系统文件），按相对路径排序。"""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        files.extend(Path(dirpath) / name for name in filenames)
    files.sort(key=lambda p: (rel(p).lower(), rel(p)))
    return files


def print_list(header: str, items: list[Path]) -> None:
    print(f"\n{header}（共 {len(items)} 个）：")
    for item in items:
        print(f"  {rel(item)}")


def report_errors(errors: list[tuple[Path, str]]) -> None:
    if not errors:
        return
    print(f"\n有 {len(errors)} 项失败：")
    for path, message in errors:
        print(f"  {rel(path)}：{message}")


def ask(expected: str, prompt: str) -> bool:
    """回答必须与 expected 完全一致（区分大小写）才算确认。"""
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer == expected


def delete_files(files: list[Path]) -> None:
    deleted = 0
    errors: list[tuple[Path, str]] = []
    for path in files:
        try:
            os.unlink(path)
            deleted += 1
        except OSError as exc:
            errors.append((path, str(exc)))
    print(f"\n已删除 {deleted} 个文件。")
    report_errors(errors)


def delete_gifs() -> None:
    gifs = [p for p in collect_files(TARGET) if p.suffix.lower() == GIF_SUFFIX]
    if not gifs:
        print("没有 GIF 文件，无需删除。")
        return
    print_list("将要删除的 GIF 文件", gifs)
    if not ask("Y", "\n输入 Y 确认删除（不可恢复）："):
        print("已取消，什么都没删。")
        return
    delete_files(gifs)


def rename_files() -> None:
    files = collect_files(TARGET)
    if not files:
        print("没有文件可重命名。")
        return
    plan = [
        (src, src.with_name(f"{index:0{NUMBER_WIDTH}d}{src.suffix}"))
        for index, src in enumerate(files, start=1)
    ]
    print(f"\n将要重命名的文件（共 {len(plan)} 个）：")
    for src, dst in plan:
        print(f"  {rel(src)}  ->  {dst.name}")
    if not ask("Y", "\n输入 Y 确认重命名（不可恢复）："):
        print("已取消，什么都没改。")
        return

    # 两阶段改名，避免目标名与树中现有文件撞名
    staged: list[tuple[Path, Path, Path]] = []
    errors: list[tuple[Path, str]] = []
    for index, (src, dst) in enumerate(plan):
        tmp = src.with_name(f".__renaming_{os.getpid()}_{index}")
        try:
            os.rename(src, tmp)
            staged.append((tmp, dst, src))
        except OSError as exc:
            errors.append((src, f"暂存失败：{exc}"))

    renamed = 0
    for tmp, dst, src in staged:
        try:
            os.rename(tmp, dst)
            renamed += 1
        except OSError as exc:
            errors.append((src, f"改名失败：{exc}"))
            try:
                os.rename(tmp, src)
            except OSError as rollback_exc:
                errors.append((tmp, f"回滚失败，文件停在临时名：{rollback_exc}"))
    print(f"\n已重命名 {renamed} 个文件。")
    report_errors(errors)


def delete_non_webp() -> None:
    files = collect_files(TARGET)
    webp = [p for p in files if p.suffix.lower() == WEBP_SUFFIX]
    if not webp:
        print("\n【拒绝执行】目标文件夹及其子文件夹里没有任何 WebP 文件。")
        print("执行后会一个文件都不剩，判定为误操作，已中止。")
        return
    targets = [p for p in files if p.suffix.lower() != WEBP_SUFFIX]
    if not targets:
        print("除 WebP 外没有其他文件，无需删除。")
        return

    print_list("将要删除的非 WebP 文件", targets)
    print(f"\n删除后保留 {len(webp)} 个 WebP 文件。")
    for round_no, expected in enumerate(("Y", "yes", "YES"), start=1):
        if not ask(expected, f"第 {round_no}/3 次确认，输入 {expected}（不可恢复）："):
            print("已取消，什么都没删。")
            return
    delete_files(targets)


def delete_empty_dirs() -> None:
    removed: list[Path] = []
    errors: list[tuple[Path, str]] = []
    for dirpath, _dirnames, _filenames in os.walk(TARGET, topdown=False):
        folder = Path(dirpath)
        if folder == TARGET:
            continue
        try:
            if any(folder.iterdir()):
                continue
            folder.rmdir()
            removed.append(folder)
        except OSError as exc:
            errors.append((folder, str(exc)))
    if not removed and not errors:
        print("没有空文件夹。")
        return
    removed.sort(key=lambda p: (rel(p).lower(), rel(p)))
    print_list("已删除的空文件夹", removed)
    report_errors(errors)


def main() -> int:
    if not TARGET.is_dir():
        print(f"目标文件夹不存在：{TARGET}")
        return 1

    actions = {
        "1": delete_gifs,
        "2": rename_files,
        "3": delete_non_webp,
        "4": delete_empty_dirs,
    }
    while True:
        print(MENU.format(target=TARGET))
        try:
            choice = input("请选择功能编号（0 退出）：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("0", "q", "Q"):
            print("已退出。")
            return 0
        action = actions.get(choice)
        if action is None:
            print("无效的编号，请输入 0-4。")
            continue
        print()
        action()
        print("\n—— 操作结束，返回菜单 ——")


if __name__ == "__main__":
    sys.exit(main())

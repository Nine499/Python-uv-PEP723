# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库定位

这不是一个 Python 包或应用，而是一组互相独立的单文件命令行工具。根目录的每个 `.py` 文件都能单独复制、单独运行；脚本之间不共享模块、不互相导入。仓库没有 `src/`、包目录、`__init__.py`、测试目录、构建脚本或 CI。

整个仓库只遵循一种运行模型：PEP 723 内联元数据 + `uv run`。README.md 是面向使用者的完整文档；本文件只记录修改仓库时需要知道的约束。

## 常用命令

运行任意脚本（唯一支持的方式）：

```bash
uv run 文件名.py
```

仓库没有 build、lint、typecheck、test 命令，也没有单测可跑。不要为了验证临时引入 pytest、ruff、pyproject.toml 或虚拟环境。

修改后的最低验证：

```bash
# 1. 语法解析全部脚本
uv run python -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('.').glob('*.py')]; print('ok')"

# 2. 两个无密钥、无网络的冒烟测试
uv run uuid49.py
echo '{}' | uv run claude_statusLine.py
```

其他常用调用：

```bash
uv run imgchest_upload.py path/to/image.png
uv run select_claudecode_api.py
uv run update_binaries.py
uv run acg_cleaner.py
```

后三个会修改真实文件或用户配置，运行前先读下文对应条目。

## 架构与运行模型

### PEP 723 是唯一的依赖清单

每个脚本的依赖写在文件头：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.27.0",
# ]
# ///
```

uv 读取后为脚本创建隔离环境并缓存。仓库中不应出现：

- `pyproject.toml`
- `requirements*.txt`
- `uv.lock`
- `.venv` / `venv`
- `uv init` 生成的项目结构

第三方依赖只加到脚本头的 `dependencies`，不要用 `pip`、`uv add` 或 `uv pip install` 往仓库装包。

### 脚本彼此独立

- 所有脚本平铺在根目录，没有共享模块。
- `.env` 解析、缓存、重试、原子写入等逻辑在各脚本内重复实现，这是刻意的：保证任意单个文件复制到别处仍可运行。
- 不要为了「复用」抽出 `common.py`、`utils.py` 或包结构；修改一个脚本时不要假设其他脚本会同步变化。

### 外部边界

| 边界 | 使用者 | 说明 |
| --- | --- | --- |
| stdin JSON | `claude_statusLine.py` | Claude Code 通过 statusLine 传入 |
| HTTPS | `deepseek_usage.py`、`opencode_usage.py`、`imgchest_upload.py`、`update_binaries.py` | 余额、用量、图床上传、GitHub release |
| `$SECRETS49` | 五个脚本 | 仓库外的密钥目录 |
| `~/.claude/settings.json` | `select_claudecode_api.py` | 合并 `env` 字段 |
| `~/.local/bin` | `update_binaries.py` | 安装或覆盖二进制 |
| 目标图片目录 | `acg_cleaner.py` | 硬编码 `TARGET`，直接删除或重命名 |

### 密钥契约

`$SECRETS49` 指向仓库外目录，包含 `.env` 和可选的 `claudecode_api.yaml`。

| 键名 | 使用脚本 |
| --- | --- |
| `deepseek-key` | `deepseek_usage.py` |
| `opencode-go-key` | `opencode_usage.py` |
| `imgchest-key` 或 `IMGCHEST_API_KEY` | `imgchest_upload.py` |
| `github-no-403`（回退 `GITHUB_TOKEN`） | `update_binaries.py` |

`.env` 的解析规则不统一：`deepseek_usage.py`、`opencode_usage.py`、`update_binaries.py` 只按第一个 `=` 切分，不支持 `export` 和注释；`imgchest_upload.py` 支持注释、`export` 前缀和引号。跨脚本统一使用最朴素的 `KEY=VALUE`：

```dotenv
deepseek-key=sk-xxxxxxxx
opencode-go-key=xxxxxxxx
imgchest-key=xxxxxxxx
github-no-403=ghp_xxxxxxxx
```

`select_claudecode_api.py` 不读 `.env`，只读 `$SECRETS49/claudecode_api.yaml`。

### 写入与破坏性操作

- `acg_cleaner.py`：删除或重命名前先打印完整清单；非 WebP 删除需要三次确认，且目录里没有任何 WebP 时拒绝执行；删除空目录不确认。
- `select_claudecode_api.py`：只合并、不删除旧键；内容不变不写；变更时用临时文件加 `os.replace`，保留权限位；不创建备份。
- `update_binaries.py`：每个工具独立下载、解包、用临时文件加 `os.replace` 安装；单个失败不影响其他工具，最终任一失败返回 1。
- 查询类脚本：缓存写在系统临时目录，TTL 300 秒，不含 key；缓存不区分账号。

### 平台假设

- 面向 WSL Ubuntu / Linux。
- `acg_cleaner.py` 的 `TARGET` 是 WSL 下访问 Windows 盘的路径。
- `update_binaries.py` 的下载 URL 全部硬编码为 Linux x86_64/amd64，且不校验哈希或签名。

## 脚本索引

| 脚本 | 作用 | 关键点 |
| --- | --- | --- |
| `acg_cleaner.py` | GIF 删除、全局重命名、非 WebP 删除、空目录删除 | 交互菜单；不可恢复；需改 `TARGET` |
| `claude_statusLine.py` | 三行状态栏 | 只读 stdin、transcript、git；速度是估算值 |
| `deepseek_usage.py` | 打印 DeepSeek 余额 | `deepseek-key`；5 分钟缓存 |
| `opencode_usage.py` | 打印 OpenCode Go 剩余用量 | 需自定义 UA；5 分钟缓存；缺 PEP 723 头 |
| `imgchest_upload.py` | 上传图片并打印直链 | `imgchest-key`；固定隐藏、匿名、NSFW |
| `select_claudecode_api.py` | 切换 Claude Code API 环境变量 | 交互选择；合并 `~/.claude/settings.json` 的 `env` |
| `update_binaries.py` | 更新 10 个 CLI 工具 | GitHub API；写入 `~/.local/bin`；支持 Range 并发下载 |
| `uuid49.py` | 生成首字符为 a-f 的 UUID | 随机、非时间有序 |

## 编辑约定

1. 新脚本放根目录，单文件，不建子目录或包。
2. 文件头必须有 PEP 723 块；只用标准库时写 `dependencies = []`。
3. 需要第三方依赖时只写进 `dependencies`，优先使用标准库。
4. 使用 `main()` 加 `if __name__ == "__main__":` 入口。
5. 密钥从环境变量或 `$SECRETS49` 读取，不写进源码、示例或默认值。
6. 保持脚本可单独复制：不新增跨脚本导入，不依赖仓库内的相对路径资源。
7. 改变命令行参数、输出格式、配置键或副作用时，同步更新 `README.md` 的对应章节与速查表。
8. 新增或删除脚本时，同步本文件的「脚本索引」和 README。

新脚本模板：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

def main() -> None:
    ...

if __name__ == "__main__":
    main()
```

## 已知例外与易踩点

- `opencode_usage.py` 目前没有 PEP 723 文件头，是仓库唯一例外。修改它时补上，并把 `requires-python` 定在 `>=3.10`（代码使用了 `X | None` 语法）。
- `acg_cleaner.py` 的菜单第 4 项删除空目录没有二次确认；第 2 项重命名会包含隐藏文件和非图片文件，序号全局连续。
- `claude_statusLine.py` 的 TTFT / TPOT / TPS 来自 transcript 落盘时间，不是精确的流式计时；git 查询超时为 150ms，超时则省略 git 段。
- `select_claudecode_api.py` 切换配置后，旧配置独有的键仍留在 `settings.json`，需要手动清理。
- `update_binaries.py` 每次都会重新下载最新 release，不比较本地版本；GitHub API 未认证时限额 60 次/小时。
- `imgchest_upload.py` 的可见性和 NSFW 标记是常量 `FORM_FIELDS`，固定为隐藏、匿名、NSFW。
- `deepseek_usage.py` 与 `opencode_usage.py` 的缓存是全局单文件，切换 key 后 5 分钟内可能仍显示旧账号数据。

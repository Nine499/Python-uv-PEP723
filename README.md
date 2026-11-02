# Python uv PEP 723 脚本集

一组可以直接用 `uv run` 运行的单文件 Python 工具。每个脚本都把 Python 版本要求和第三方依赖写在自己的文件头里，克隆仓库后不需要创建虚拟环境、不需要 `pip install`、也不需要在仓库里放 `pyproject.toml` 或 `requirements.txt`。

仓库里的脚本彼此独立，可以单独复制到任何目录使用。它们覆盖这些场景：

- 批量清理图片文件夹
- 渲染 Claude Code 状态栏
- 查询 DeepSeek 余额、OpenCode 用量
- 上传图片到 imgchest 图床
- 切换 Claude Code 的 API 环境变量
- 批量更新 `~/.local/bin` 下的命令行工具
- 生成指定格式的 UUID

---

## 目录

- [项目简介](#项目简介)
- [设计原则](#设计原则)
- [目录结构](#目录结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [脚本速查表](#脚本速查表)
- [通用约定](#通用约定)
  - [uv run 与 PEP 723](#uv-run-与-pep-723)
  - [SECRETS49 密钥目录](#secrets49-密钥目录)
  - [缓存](#缓存)
  - [原子写入](#原子写入)
- [脚本详解](#脚本详解)
  - [acg_cleaner.py](#acg_cleanerpy)
  - [claude_statusLine.py](#claude_statuslinepy)
  - [deepseek_usage.py](#deepseek_usagepy)
  - [opencode_usage.py](#opencode_usagepy)
  - [imgchest_upload.py](#imgchest_uploadpy)
  - [select_claudecode_api.py](#select_claudecode_apipy)
  - [update_binaries.py](#update_binariespy)
  - [uuid49.py](#uuid49py)
- [新增脚本指南](#新增脚本指南)
- [常见问题](#常见问题)
- [已知限制与注意事项](#已知限制与注意事项)

---

## 项目简介

本仓库把「一次性小工具」做成可长期复用、可随手复制、无环境负担的脚本集合。

每个脚本都满足同一条约束：

```bash
uv run 文件名.py
```

`uv` 会读取文件开头的 PEP 723 内联元数据，为这个脚本准备一个隔离的临时环境，安装声明的依赖，然后执行脚本。环境由 uv 缓存，重复运行不会反复安装。

这种组织方式适合：

- 个人工具箱、临时自动化
- 不方便维护项目级依赖的机器
- 需要单文件分发、复制即用的场景

不适合：

- 需要多模块、多包结构的应用
- 需要严格锁定全部传递依赖的生产部署
- 需要测试框架、CI 流水线的团队项目

---

## 设计原则

1. **单文件交付**：一个脚本就是一件工具，不拆模块，不建包。
2. **依赖内联**：第三方依赖只写在 PEP 723 的 `dependencies` 中，不在仓库里安装。
3. **仓库零环境**：不提交 `.venv`、`pyproject.toml`、`uv.lock`、`requirements*.txt`。
4. **密钥外置**：API key 一律从仓库外的 `$SECRETS49` 目录读取，不进 Git。
5. **危险操作先展示**：删除、重命名、覆盖配置前先打印完整影响范围，并要求确认；写入配置使用临时文件加原子替换。
6. **失败可见**：错误写到 stderr，能返回退出码的地方返回非零退出码，不静默吞掉失败。

---

## 目录结构

```text
Python-uv-PEP723/
├── README.md                  # 本文档
├── CLAUDE.md                  # 本仓库的脚本编写规则
├── .gitignore                 # 忽略字节码、虚拟环境、编辑器文件
├── acg_cleaner.py             # 图片文件夹批量清理
├── claude_statusLine.py       # Claude Code 状态栏渲染
├── deepseek_usage.py          # DeepSeek 余额查询
├── imgchest_upload.py         # imgchest 图床上传
├── opencode_usage.py          # OpenCode Go 用量查询
├── select_claudecode_api.py   # 切换 Claude Code API 配置
├── update_binaries.py         # 批量更新 ~/.local/bin 工具
└── uuid49.py                  # 生成 UUID
```

仓库根目录不放任何 Python 环境文件。所有脚本都在根目录平铺，直接运行即可。

---

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Linux；当前主要面向 WSL Ubuntu |
| uv | 0.13 及以上（本仓库在 0.13.6 上验证） |
| Python | 各脚本要求不同，见下方表格；uv 会为每个脚本选择可用解释器 |
| git | 仅 `claude_statusLine.py` 用于读取仓库状态 |
| 网络 | 查询余额、查询用量、上传图片、更新二进制时需要 |
| 密钥目录 | `$SECRETS49`，仅部分脚本需要 |

各脚本声明的 Python 版本：

| 脚本 | `requires-python` | 第三方依赖 |
| --- | --- | --- |
| `acg_cleaner.py` | `>=3.10` | 无 |
| `claude_statusLine.py` | `>=3.11` | 无 |
| `deepseek_usage.py` | `>=3.11` | 无 |
| `imgchest_upload.py` | `>=3.12` | `httpx>=0.27.0` |
| `opencode_usage.py` | 未声明 PEP 723 元数据 | 无 |
| `select_claudecode_api.py` | `>=3.11` | `PyYAML>=6.0.2,<7` |
| `update_binaries.py` | `>=3.12` | `httpx[http2]>=0.27.0`、`tqdm>=4.66.0` |
| `uuid49.py` | `>=3.11` | 无 |

> 如果本机缺少 `requires-python` 指定的解释器，请先自行安装对应版本。按本机约定，不要让 uv 自动下载 Python。

---

## 快速开始

```bash
git clone <仓库地址> Python-uv-PEP723
cd Python-uv-PEP723

# 无依赖、无配置，直接可跑
uv run uuid49.py
```

第一次运行某个脚本时，uv 会为它准备隔离环境。只有声明了第三方依赖的脚本才会经历下载和安装，之后走缓存。

需要密钥的脚本，先配置 `$SECRETS49`：

```bash
export SECRETS49="$HOME/.secrets49"
mkdir -p "$SECRETS49"
$EDITOR "$SECRETS49/.env"
```

`.env` 的最小示例：

```dotenv
deepseek-key=sk-xxxxxxxx
opencode-go-key=xxxxxxxx
imgchest-key=xxxxxxxx
github-no-403=ghp_xxxxxxxx
```

建议把 `export SECRETS49=...` 写进 shell 启动文件，否则每个新终端都要重新导出。

---

## 脚本速查表

| 脚本 | 一句话用途 | 是否需要 `$SECRETS49` | 是否交互 | 是否修改系统 |
| --- | --- | --- | --- | --- |
| `acg_cleaner.py` | 删除 GIF / 重命名 / 删非 WebP / 删空目录 | 否 | 是，菜单 + 确认 | 是，直接删除文件 |
| `claude_statusLine.py` | 从 stdin JSON 渲染三行状态栏 | 否 | 否 | 否 |
| `deepseek_usage.py` | 打印 DeepSeek 账户余额 | 是，`deepseek-key` | 否 | 写缓存文件 |
| `opencode_usage.py` | 打印 OpenCode Go 剩余用量 | 是，`opencode-go-key` | 否 | 写缓存文件 |
| `imgchest_upload.py` | 上传图片并打印直链 | 是，`imgchest-key` 或 `IMGCHEST_API_KEY` | 否 | 上传到外部图床 |
| `select_claudecode_api.py` | 把选中配置合并进 `~/.claude/settings.json` | 是，另需 `claudecode_api.yaml` | 是，编号选择 | 是，改写用户配置 |
| `update_binaries.py` | 并发更新 10 个命令行工具 | 可选，`github-no-403` / `GITHUB_TOKEN` | 否 | 是，覆盖 `~/.local/bin` |
| `uuid49.py` | 生成首字符为 a-f 的 UUID | 否 | 否 | 否 |

---

## 通用约定

### uv run 与 PEP 723

脚本头部形如：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.27.0",
# ]
# ///
```

- 只使用 `uv run 文件名.py` 运行。
- 不使用 `python 文件名.py` 直接运行，避免落到系统解释器、缺少依赖或版本不符。
- 不执行 `pip install`、`uv pip install`、`uv add`，不在仓库里创建 `.venv`。
- 依赖只在脚本头部声明。需要新依赖时改 `dependencies`，然后重新 `uv run`。

uv 会为每个脚本单独建环境。不同脚本的依赖互不影响，也不会污染仓库目录。

### SECRETS49 密钥目录

`$SECRETS49` 指向一个仓库之外的目录，当前约定包含两个文件：

```text
$SECRETS49/
├── .env                  # 键值配置，供多个脚本读取
└── claudecode_api.yaml   # Claude Code API 配置预设
```

`.env` 的解析方式在不同脚本间略有差异：

| 脚本 | 读取的键 | `.env` 解析规则 |
| --- | --- | --- |
| `deepseek_usage.py` | `deepseek-key` | 按第一个 `=` 切分；键名去空白；值去首尾空白和引号；不识别注释与 `export` |
| `opencode_usage.py` | `opencode-go-key` | 同上 |
| `imgchest_upload.py` | `IMGCHEST_API_KEY` 或 `imgchest-key` | 忽略空行和 `#` 注释；支持 `export ` 前缀；值去引号 |
| `update_binaries.py` | `github-no-403` | 按第一个 `=` 切分；值去引号；找不到时回退到 `$GITHUB_TOKEN` |
| `select_claudecode_api.py` | 不使用 `.env` | 单独读取 `claudecode_api.yaml` |

为了兼容全部脚本，`.env` 请使用最朴素的格式：

```dotenv
deepseek-key=sk-xxxxxxxx
opencode-go-key=xxxxxxxx
imgchest-key=xxxxxxxx
github-no-403=ghp_xxxxxxxx
```

不要写 `export` 前缀，不要在值后面追加行内注释，不要给键名加空格。

### 缓存

两个查询脚本会把结果缓存在系统临时目录，默认 TTL 为 5 分钟：

| 脚本 | 缓存文件 |
| --- | --- |
| `deepseek_usage.py` | `$TMPDIR/deepseek_usage_cache.json` |
| `opencode_usage.py` | `$TMPDIR/opencode_usage_cache.json` |

- 缓存只包含接口响应，不包含 API key。
- 5 分钟内重复运行不会发网络请求。
- 切换账号或改了 key 后，需要手动删除缓存文件才能立刻生效。
- 缓存写入失败只打印警告，不影响本次输出。

### 原子写入

涉及覆盖文件的两个脚本都使用「同目录临时文件 + `os.replace`」：

- `select_claudecode_api.py` 写 `~/.claude/settings.json`
- `update_binaries.py` 安装二进制到 `~/.local/bin`

这样即使进程在写入中途被中断，也不会留下写了一半的目标文件。`select_claudecode_api.py` 还会保留原文件的权限位，并且内容没有变化时不写入。

---

## 脚本详解

### acg_cleaner.py

**用途**：对一个图片文件夹做四类批量清理操作。

**元数据**：`requires-python >= 3.10`，无第三方依赖。

**运行**：

```bash
uv run acg_cleaner.py
```

**目标目录**：硬编码在脚本顶部：

```python
TARGET = Path("/mnt/c/Users/Forty/acg/1")
```

这是 WSL 下访问 Windows 盘符的路径。换机器或换目录时必须先修改这一行。

**交互菜单**：

```text
========== ACG 清理工具 ==========
目标文件夹：/mnt/c/Users/Forty/acg/1
  1. 删除所有 GIF 文件（含子文件夹）
  2. 把所有文件重命名为 0000001 递增序号（保留扩展名）
  3. 删除所有非 WebP 文件（需三次确认）
  4. 删除所有空文件夹
  0. 退出
==================================
```

输入 `0`、`q` 或 `Q` 退出。输入其他无效内容会提示重新输入。每次操作结束后回到菜单，直到主动退出。

**功能 1：删除 GIF**

1. 递归收集 `TARGET` 下所有扩展名为 `.gif` 的文件，大小写不敏感。
2. 打印完整文件列表和总数。
3. 要求输入大写 `Y` 才执行；其他任何输入都取消。
4. 逐个 `os.unlink`，最后报告删除数量和失败项。

**功能 2：重命名**

1. 递归收集所有文件，包括隐藏文件。
2. 按相对路径排序，先按小写路径比较，再按原路径比较，保证顺序稳定。
3. 生成计划：第 1 个文件改名为 `0000001`，第 2 个为 `0000002`，依此类推，扩展名保留。序号宽度固定 7 位。
4. 打印全部「旧路径 -> 新文件名」。
5. 输入大写 `Y` 才执行。
6. 使用两阶段改名：先把源文件改成 `.__renaming_<pid>_<index>` 临时名，全部暂存成功后再改成目标名，避免目标名与树中现有文件撞名。
7. 第二阶段失败时尝试回滚到原名；回滚失败会明确报告文件停在哪个临时名。

注意：

- 重命名发生在原目录内，不会把子目录里的文件移动到根目录。
- 所有文件都会参与编号，包括 `.txt`、`.nfo` 等非图片文件。
- 编号是全局连续的，不同子目录共享同一套序号。

**功能 3：删除非 WebP**

这是破坏性最强的操作，带三重保护：

1. 先检查目标树里是否存在至少一个 `.webp`。如果一个都没有，直接拒绝执行，避免把整个目录删空。
2. 打印所有将被删除的非 WebP 文件，以及删除后会保留多少个 WebP。
3. 依次要求输入三次完全匹配的确认词：`Y`、`yes`、`YES`，区分大小写。
4. 任何一次输入不匹配都会取消，不删除任何文件。

**功能 4：删除空文件夹**

1. 自底向上遍历 `TARGET` 的所有子目录。
2. 跳过 `TARGET` 本身。
3. 目录内没有任何条目时执行 `rmdir`。
4. 打印删除的目录列表和失败项。

这一项**没有二次确认**，选中后立即执行。空目录通常风险较低，但如果包含挂载点或特殊目录，`rmdir` 会失败并记录错误。

**退出码**：目标目录不存在时为 `1`；正常退出为 `0`。删除失败不会改变退出码，只在输出中列出。

**不可恢复**：所有删除都直接作用于文件系统，没有回收站、没有备份。执行前请确认目标目录正确。

---

### claude_statusLine.py

**用途**：作为 Claude Code 的 `statusLine` 命令，从 stdin 读取 JSON，输出三行状态信息。

**元数据**：`requires-python >= 3.11`，无第三方依赖。

**配置方式**：在 `~/.claude/settings.json` 中加入：

```json
{
  "statusLine": {
    "type": "command",
    "command": "uv run /home/forty-wsl/github/Python-uv-PEP723/claude_statusLine.py"
  }
}
```

建议使用脚本绝对路径，因为 Claude Code 启动时的 `PATH` 不一定包含你交互式 shell 里的全部路径。如果连 `uv` 也找不到，把 `uv` 换成 `command -v uv` 输出的绝对路径。

**输入**：Claude Code 通过 stdin 传入一个 JSON 对象。脚本只读这些字段，缺字段时降级显示：

| 字段 | 用途 |
| --- | --- |
| `model.id` | 模型 ID，缺失显示 `unknown` |
| `effort.level` | 推理强度，缺失显示 `-` |
| `context_window.context_window_size` | 上下文窗口大小，格式化为 K/M |
| `context_window.used_percentage` | 已用百分比，默认 0 |
| `workspace.current_dir` | 当前目录 |
| `cwd` | 当前目录的回退字段 |
| `workspace.project_dir` | 当前目录的第二个回退字段 |
| `cost.total_lines_added` | 本次会话新增行数 |
| `cost.total_lines_removed` | 本次会话删除行数 |
| `transcript_path` | 会话 transcript 文件路径 |
| `prompt_cache.hit_ratio` | 缓存命中率，支持 0~1 小数或百分数 |

stdin 不是合法 JSON 或不是对象时，按空对象处理，不报错。

**输出**：最多三行，空行会被跳过。

第一行，模型与上下文：

```text
model: claude-opus-4-5(high) | window[1M]: 23%
```

窗口大小向下取整：大于等于 100 万显示 `1M` 这类 M 值，大于等于 1000 显示 `200K`，否则显示原始数字。

第二行，目录、Git 状态、代码量：

```text
dir: Python-uv-PEP723 | git:master | ↑1 | ↓2 | !1 | +3 | ~4 | -5 | ?6 | code:+120/-8
```

Git 部分通过 `git status --porcelain=v2 --branch --untracked-files=normal` 获取，超时 150 毫秒。超时或失败时整段 Git 信息省略，不影响其他内容。

Git 标记含义：

| 标记 | 含义 |
| --- | --- |
| `↑N` | 本地领先上游 N 个提交 |
| `↓N` | 落后上游 N 个提交 |
| `no-up` | 当前分支没有上游 |
| `no-ab` | 有上游但 Git 未提供领先/落后计数 |
| `sync` | 与上游完全同步 |
| `!N` | 冲突文件数 |
| `+N` | 已暂存变更数 |
| `~N` | 工作区已修改数 |
| `-N` | 删除数 |
| `?N` | 未跟踪文件数 |
| `clean` | 工作区干净 |

分支引用规则：

- 正常分支显示分支名，超过 32 字符截断并加 `…`。
- detached HEAD 且能拿到 OID 时显示 `@` 加前 7 位 OID。
- 其他情况显示 `unknown`。

一个已删除文件只在 `-N` 中计数一次；同时存在暂存和不暂存变更的文件会分别计入 `+N` 和 `~N`。这组数字用于快速观察，不追求与 `git status` 输出逐行等价。

第三行，请求速度与缓存：

```text
ttft: 1.2s | tpot: 25.0ms | tps: 40 | cache: 92%
```

- **TTFT**：请求发出到首个回复内容块的时间差，包含 thinking 时间。
- **TPOT**：整段请求耗时除以输出 token 数，即每个输出 token 的平均耗时。
- **TPS**：输出 token 数除以整段请求耗时。
- **cache**：`prompt_cache.hit_ratio`；小于等于 1 按小数换算成百分比，大于 1 直接当百分数；非数字显示 `0%`。

**速度数据来源与精度**：

状态栏输入本身不带耗时字段。脚本从 `transcript_path` 指向的文件末尾读取最多 256 KB，倒序寻找最近一次主线程请求，并用 transcript 中记录的时间戳估算：

- 只处理 `isSidechain` 不为真的记录。
- 先收集 `type == "assistant"` 的回复，遇到 `type == "api-request"` 时用请求 `id` 与回复 `requestRef` 配对。
- 时间戳来自记录落盘时刻，不是精确的流式首 token 时间，因此 TTFT 和 TPS 都是近似值。
- transcript 为空、路径缺失、解析失败或找不到配对请求时，三项显示 `-`，缓存仍正常显示。

**性能**：主路径只解析 stdin、跑一次带 150ms 超时的 git、读一次文件尾部、拼字符串。不读设置文件，不发网络请求。

**退出码**：始终返回 `0`。

---

### deepseek_usage.py

**用途**：查询 DeepSeek 账户余额，输出一行供状态栏或提示符使用。

**元数据**：`requires-python >= 3.11`，无第三方依赖，使用标准库 `urllib`。

**运行**：

```bash
uv run deepseek_usage.py
```

**接口**：`GET https://api.deepseek.com/user/balance`，使用 `Authorization: Bearer <key>`，超时 10 秒。

**密钥**：从 `$SECRETS49/.env` 读取 `deepseek-key`。未设置 `SECRETS49`、文件不可读、键不存在时，直接打印原因并退出。

**输出示例**：

```text
DS余额：12.34
```

规则：

- 接口返回 `is_available == false` 时输出 `DS余额：不可用`。
- 优先选择 `currency == "CNY"` 的余额项；没有 CNY 时取列表第一项。
- 金额格式保留两位小数，并去掉末尾的 `0` 和小数点：`12.00` 输出 `12`，`12.30` 输出 `12.3`。
- 响应中没有 `balance_infos` 或列表为空时报错退出。

**缓存**：

- 路径：`<系统临时目录>/deepseek_usage_cache.json`，通常是 `/tmp/deepseek_usage_cache.json`。
- TTL：300 秒。
- 命中缓存时完全不读 key，也不发请求。
- 只有成功获取新数据时才写缓存；写入失败仅在 stderr 打印警告。

**exit code**：成功 `0`；任何配置、网络、响应错误均为 `1`，错误信息直接作为 `sys.exit` 的消息输出到 stderr。

**注意**：

- 缓存不区分 API key。切换账号后 5 分钟内仍会显示旧账号余额，需手动删除缓存文件。
- `.env` 解析不识别 `export` 前缀和注释。

---

### opencode_usage.py

**用途**：查询 OpenCode Go 的滚动 5 小时、7 天、月度配额剩余量，输出一行。

**元数据**：**这个脚本没有 PEP 723 内联元数据块**，是本仓库当前的例外。它只用标准库，因此 `uv run` 仍能通过回退解释器执行，但无法锁定 Python 版本。

**运行**：

```bash
uv run opencode_usage.py
```

**接口**：`GET https://opencode.ai/zen/go/v1/usage`，超时 30 秒。

两个特殊点：

- 必须发送自定义 `User-Agent: opencode-usage/1.0`，默认的 `Python-urllib` UA 会被接口以 403 拒绝。
- 请求头带 `Authorization: Bearer <key>` 和 `Accept: application/json`。

**密钥**：从 `$SECRETS49/.env` 读取 `opencode-go-key`。

**输出示例**：

```text
剩余 5h:98%(9m) 7d:99%(1d12h) 1m:100%(29d)
```

三段分别是：

| 标签 | 接口字段 | 显示精度 |
| --- | --- | --- |
| `5h` | `usage.rolling` | 小时/分钟，自动跳过高位零 |
| `7d` | `usage.weekly` | 天/小时，自动跳过高位零 |
| `1m` | `usage.monthly` | 天，自动跳过高位零 |

**百分比**：

- 接口给的是已用百分比，脚本换算成剩余百分比：`100 - used`，四舍五入取整，范围限制在 0~100。
- 配额对象里 `status == "rate-limited"` 时直接显示 `0%`。
- 字段缺失或类型不对显示 `--`。

**重置时间**：

- 从 `resetsAt` 的 ISO 8601 字符串解析，计算与当前时间的差值，最小为 0。
- 例如剩余 90 秒显示 `1m`，不会显示 `0h1m`。
- 无法解析时显示 `--`。

**缓存**：

- 路径：`<系统临时目录>/opencode_usage_cache.json`。
- TTL：300 秒；命中时直接格式化缓存中的 `usage`。
- 写缓存失败只警告。

**exit code**：成功 `0`；配置、网络、响应错误均为 `1`。

**注意**：与 DeepSeek 相同，缓存不区分账号。

---

### imgchest_upload.py

**用途**：把一张图片上传到 imgchest，打印返回的直链，每行一个。

**元数据**：`requires-python >= 3.12`，依赖 `httpx>=0.27.0`。

**运行**：

```bash
uv run imgchest_upload.py 图片路径
```

只接受一个参数，必须指向普通文件。参数数量不对或文件不存在时返回退出码 `1`。

**密钥**：从 `$SECRETS49/.env` 读取，候选键名按顺序为：

1. `IMGCHEST_API_KEY`
2. `imgchest-key`

取第一个非空值。这个脚本的 `.env` 解析支持空行、`#` 注释、`export ` 前缀和引号包裹的值。

**上传参数**：固定为：

```python
FORM_FIELDS = {"privacy": "hidden", "anonymous": "1", "nsfw": "1"}
```

即：隐藏帖、匿名上传、标记 NSFW。需要修改可见性或标记时，改这一行。

**请求**：

- `POST https://api.imgchest.com/v1/post`
- 字段名 `images[]`，MIME 类型由扩展名推断，猜不到时使用 `application/octet-stream`
- 连接超时 10 秒，总超时 60 秒，跟随重定向

**重试**：

- 最多 3 次。
- 网络传输错误、可重试状态码会触发重试，等待时间指数退避：1 秒、2 秒。
- 可重试状态码：`408`、`409`、`425`、`429`、`500`、`502`、`503`、`504`。
- 本地文件读取错误不重试，直接失败。

**输出**：

```text
https://imgchest.com/p/xxxxx
```

接口响应中的 `data.images[].link` 会全部打印，顺序与响应一致。响应不是 JSON、缺少字段、链接为空都视为失败。

**退出码**：

| 退出码 | 含义 |
| --- | --- |
| `0` | 上传成功 |
| `1` | 参数错误、文件不存在、配置错误 |
| `2` | HTTP 状态异常或响应格式不符合预期 |
| `3` | 网络错误且重试耗尽 |

错误信息写 stderr；成功时 stdout 只有链接，便于管道处理。

---

### select_claudecode_api.py

**用途**：从 `$SECRETS49/claudecode_api.yaml` 选择一个预设，把它的键值合并进 `~/.claude/settings.json` 的 `env` 字段。

**元数据**：`requires-python >= 3.11`，依赖 `PyYAML>=6.0.2,<7`。

**运行**：

```bash
uv run select_claudecode_api.py
```

**配置文件**：`$SECRETS49/claudecode_api.yaml`，必须是非空映射，结构为「配置名 -> 字符串键值映射」：

```yaml
official:
  ANTHROPIC_BASE_URL: https://api.anthropic.com
  ANTHROPIC_AUTH_TOKEN: sk-ant-xxxxxxxx

relay-a:
  ANTHROPIC_BASE_URL: https://relay-a.example.com
  ANTHROPIC_AUTH_TOKEN: sk-xxxxxxxx

relay-b:
  ANTHROPIC_BASE_URL: https://relay-b.example.com
  ANTHROPIC_AUTH_TOKEN: sk-yyyyyyyy
```

约束：

- 顶层必须是非空对象。
- 每个配置名下的值必须是对象。
- 键和值都必须是字符串，数字、布尔值、列表都会报错。

**交互**：

```text
可用配置：
  1. official
  2. relay-a
  3. relay-b
请选择配置编号：
```

输入必须落在 `1..N` 范围内，非法输入会提示后重新询问。`Ctrl+C` 返回退出码 `130`，EOF 视为配置错误。

**合并语义**：

- 读取 `~/.claude/settings.json`；文件不存在时按空对象处理。
- 只合并到 `env` 字段。
- `env` 中已有的其他键保留，重叠键被选中的配置覆盖。
- `settings.json` 中 `env` 不是对象时报错退出。
- 其他顶层字段保持不变。

**写入**：

1. 序列化为两空格缩进的 JSON，末尾加换行。
2. 与现有内容完全相同则不写，输出「无变化」。
3. 有变化时先写入同目录临时文件 `.settings.json.<pid>.tmp`，保留原文件权限位（新文件默认 `0644`），再用 `os.replace` 原子替换。
4. 临时文件在 `finally` 中清理。

**输出**：

```text
已更新: 配置 'official' 已合并到 /home/user/.claude/settings.json 的 env。
```

或：

```text
无变化: 配置 'official' 已合并到 /home/user/.claude/settings.json 的 env。
```

**exit code**：成功 `0`；配置错误 `1`；`Ctrl+C` 为 `130`。

**注意**：

- 这是覆盖用户级配置的操作，脚本不创建备份。
- 合并只增不删。从包含额外键的配置切换到另一个配置时，旧配置独有的键会留在 `settings.json` 里，需要手动清理。
- Claude Code 可能需要重启或重新加载会话后才会使用新的环境变量。

---

### update_binaries.py

**用途**：并发检查并更新 `~/.local/bin` 下的一组命令行工具。

**元数据**：`requires-python >= 3.12`，依赖 `httpx[http2]>=0.27.0`、`tqdm>=4.66.0`。

**运行**：

```bash
uv run update_binaries.py
```

**管理的工具**：

| 安装名 | 上游仓库 | 下载产物 | 从归档提取 |
| --- | --- | --- | --- |
| `qdns` | `natesales/q` | `q_<ver>_linux_amd64.tar.gz` | `q` |
| `fzf` | `junegunn/fzf` | `fzf-<ver>-linux_amd64.tar.gz` | `fzf` |
| `yazi` | `sxyazi/yazi` | `yazi-x86_64-unknown-linux-gnu.zip` | `yazi`、`ya` |
| `starship` | `starship/starship` | `starship-x86_64-unknown-linux-gnu.tar.gz` | `starship` |
| `lazygit` | `jesseduffield/lazygit` | `lazygit_<ver>_linux_x86_64.tar.gz` | `lazygit` |
| `zoxide` | `ajeetdsouza/zoxide` | `zoxide-<ver>-x86_64-unknown-linux-musl.tar.gz` | `zoxide` |
| `yq` | `mikefarah/yq` | 直接下载 `yq_linux_amd64` | 无需解包 |
| `yt-dlp` | `yt-dlp/yt-dlp` | 直接下载 `yt-dlp` | 无需解包 |
| `tcping` | `nodeseeker/tcping` | `tcping-linux-amd64.zip` | `tcping` |
| `herdr` | `herdrdev/herdr` | 直接下载 `herdr-linux-x86_64` | 无需解包 |

所有产物都硬编码为 Linux x86_64/amd64。换平台需要修改 `TOOLS` 中对应的 `url`。

**单个工具的更新流程**：

1. 请求 `https://api.github.com/repos/<repo>/releases/latest`，取 `tag_name` 并去掉前缀 `v`。
2. 把版本号填入下载 URL 模板。
3. 下载到临时目录。
4. 如果是归档，只按文件名（大小写不敏感）提取需要的成员，不落盘其余内容。
5. 复制到目标目录的同目录临时文件，`chmod 755`，再用 `os.replace` 原子替换。
6. 打印安装路径和成功标记。

**GitHub API Token**：

- 优先读取 `$SECRETS49/.env` 的 `github-no-403`。
- 找不到时回退到环境变量 `GITHUB_TOKEN`。
- Token 只加在 `api.github.com` 的请求头中，不会发给下载域名。
- 未认证的 GitHub API 每小时只有 60 次额度，10 个工具连续运行可能触发 403；配置 Token 后额度更高。

**下载策略**：

- 先用 `Range: bytes=0-0` 探测：
  - 返回 `200`：服务器不支持分段，直接流式下载整个响应体。
  - 返回 `206`：支持分段，从 `Content-Range` 取总大小。
- 总大小小于 2 MB，或拿不到总大小时，单流下载。
- 否则切成最多 5 段并发下载，用 `os.pwrite` 按偏移写入同一个文件。
- 每段结束校验写入长度，响应被截断时标记为可重试错误。
- 下载进度通过 tqdm 显示，工具名和版本写在进度条描述里。

**并发与重试**：

- 最多同时更新 3 个工具（`CONCURRENCY = 3`）。
- 网络错误和状态码 `408`、`425`、`429`、`500`、`502`、`503`、`504` 会重试，最多 3 次，等待时间为 1 秒、2 秒。
- 单个工具失败不会中断其他工具，失败信息标红打印，最后汇总。

**输出示例**：

```text
Geek Updater Started
  ✓ /home/user/.local/bin/fzf
  ✓ /home/user/.local/bin/yazi, /home/user/.local/bin/ya
  ...
Result: 10/10 updated
```

**exit code**：全部成功 `0`；任意一个工具失败 `1`。

**注意**：

- 每次都下载最新 release，不比较本地版本，也不保存版本记录。所有工具都会重新下载，即使本地已是最新。
- 不校验哈希或签名，只依赖 HTTPS。对来源不完全信任时，请自行加校验。
- 直接下载型工具（`yq`、`yt-dlp`、`herdr`）仍会调用 GitHub API 获取版本号用于显示，因此同样受 API 限额影响。
- `~/.local/bin` 必须已在 `PATH` 中，否则更新后仍可能调用到旧版本。

---

### uuid49.py

**用途**：生成一个随机 UUID，并保证字符串首字符落在 `a` 到 `f` 之间。

**元数据**：`requires-python >= 3.11`，无第三方依赖。

**运行**：

```bash
uv run uuid49.py
```

**行为**：

1. 用 `secrets.randbits(128)` 生成 128 位随机数。
2. 把版本位设为 `6`（UUIDv6 标记）。
3. 把变体位设为 RFC 4122 变体（`10`）。
4. 检查最高 4 位；如果小于 `0xA`（即首字符是 `0` 到 `9`），重新生成。
5. 满足条件后打印一个 UUID 并退出。

输出示例：

```text
a3f1c2d4-5e6f-6a7b-8c9d-0e1f2a3b4c5d
```

**注意**：

- 版本位虽然标记为 v6，但时间字段是随机的，**不按时间排序**，不要把它当真正的 UUIDv6 使用。
- 每次调用只输出一个 UUID，进程随即结束。
- 脚本没有 `main()` 入口保护，导入模块会直接执行生成逻辑；只适合作为命令行脚本运行。

---

## 新增脚本指南

仓库规则写在 `CLAUDE.md`，新增脚本时逐条遵守：

1. **单文件**：脚本直接放在仓库根目录，不建包、不建子模块。
2. **PEP 723 元数据**：文件开头必须是 `# /// script` 到 `# ///` 的注释块。
3. **声明依赖**：第三方依赖全部写进 `dependencies = [...]`；只用标准库时写空列表。
4. **不落环境**：不创建 `.venv`，不加 `pyproject.toml`、`requirements*.txt`、`uv.lock`。
5. **固定运行方式**：确保 `uv run 文件名.py` 可以直接运行。
6. **密钥外置**：需要密钥时从 `$SECRETS49` 读取，不在代码里写死。

模板：

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///

def main() -> None:
    ...

if __name__ == "__main__":
    main()
```

自检清单：

- [ ] 文件头 PEP 723 块格式正确，`dependencies` 是合法 TOML 数组
- [ ] `uv run 文件名.py` 在干净环境下可以启动
- [ ] 没有写入仓库目录的副作用
- [ ] 破坏性操作有确认或明确的拒绝条件
- [ ] 错误信息可读，失败不静默
- [ ] 密钥只从环境变量或 `$SECRETS49` 读取
- [ ] README 的脚本速查表和详解章节已同步更新

---

## 常见问题

### 第一次运行很慢

uv 正在为脚本创建隔离环境并安装依赖。只有声明了第三方依赖的脚本会明显变慢，后续运行走缓存。想确认 uv 状态可以运行 `uv cache dir`。

### 提示「环境变量 SECRETS49 未设置」

```bash
export SECRETS49="$HOME/.secrets49"
```

并确保该目录下存在对应文件。这个变量不会自动继承到已经打开的其它终端或图形界面程序，需要写进 shell 启动文件。

### 提示无法读取 `$SECRETS49/.env`

检查目录和文件是否存在、当前用户是否有读权限：

```bash
ls -l "$SECRETS49/.env"
```

### 查询结果一直是旧的

两个查询脚本有 5 分钟缓存。删除缓存文件后重跑：

```bash
rm -f /tmp/deepseek_usage_cache.json /tmp/opencode_usage_cache.json
```

实际路径以 `uv run python -c "import tempfile; print(tempfile.gettempdir())"` 的输出为准。

### 状态栏不显示或显示不全

按顺序检查：

1. `settings.json` 中 `statusLine.command` 的路径是否正确。
2. Claude Code 所在环境能否找到 `uv`；必要时在命令里写 `uv` 的绝对路径。
3. 手动喂一段 JSON 测试：

```bash
echo '{}' | uv run /home/forty-wsl/github/Python-uv-PEP723/claude_statusLine.py
```

4. Git 信息缺失通常是因为 `git status` 超过 150 毫秒，或当前目录不在 Git 仓库内。

### 上传图片返回退出码 2

HTTP 状态异常或响应结构不符合预期。stderr 会打印状态码和响应正文，据此判断是 key 无效、额度问题还是接口变更。退出码 3 表示网络错误且三次重试都失败，先检查网络和代理。

### 更新工具时 GitHub 返回 403

未认证的 GitHub API 每小时只有 60 次请求。把 Personal Access Token 写进 `$SECRETS49/.env`：

```dotenv
github-no-403=ghp_xxxxxxxx
```

或导出 `GITHUB_TOKEN`。

### 切换 API 配置后旧变量还在

`select_claudecode_api.py` 只做合并，不删除旧键。手动编辑 `~/.claude/settings.json` 的 `env`，删掉不再需要的键，然后重启 Claude Code。

### 为什么不直接用 `python 文件名.py`

系统解释器版本可能低于脚本要求，也缺少第三方依赖。PEP 723 的价值就是让运行方式和依赖声明绑定在文件本身，统一走 `uv run`。

### 能不能把脚本复制到别处用

可以。每个脚本都是自包含的，复制单个 `.py` 文件到任意目录后仍然可以用 `uv run` 运行。依赖 `$SECRETS49` 的脚本需要目标机器同样配置密钥目录。

---

## 已知限制与注意事项

1. **`acg_cleaner.py` 的目标目录硬编码**：`/mnt/c/Users/Forty/acg/1` 是作者机器的 WSL 路径，其他环境必须先改 `TARGET`。
2. **`opencode_usage.py` 缺少 PEP 723 元数据**：与其他脚本不一致，无法锁定 Python 版本和依赖。按仓库规则应补上文件头。
3. **`update_binaries.py` 只支持 Linux x86_64**：下载 URL 全部硬编码为该平台；也不校验哈希或签名。
4. **状态栏速度是估算值**：TTFT、TPOT、TPS 基于 transcript 落盘时间，不等于真实流式计时，只适合观察趋势。
5. **查询缓存不区分账号**：DeepSeek 与 OpenCode 的缓存都是全局单文件，切换 key 后 5 分钟内可能显示旧数据。
6. **API 配置合并只增不删**：切换预设不会清理旧的环境变量，需要手动维护。
7. **没有自动化测试**：仓库没有测试框架，也没有 CI。修改脚本后需要手动运行验证。
8. **密钥解析规则不统一**：不同脚本对 `.env` 的解析能力不同，统一使用朴素的 `KEY=VALUE` 格式最安全。
9. **破坏性操作没有回收站**：`acg_cleaner.py` 的删除和重命名不可恢复；`select_claudecode_api.py` 覆盖配置时不自动备份。
10. **脚本面向个人工作流**：路径、键名、工具列表、下载平台都带有明显的本机特征，迁移到其他机器时需要逐项核对。

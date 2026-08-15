# CLAUDE.md

本仓库所有 Python 代码按需以单文件脚本存放于根目录。编写 Python 时必须遵守：

## 硬性规则

- 单文件 `.py` 脚本，使用 **PEP 723 内联脚本元数据**：文件头以 `# /// script` 开始、`# ///` 结束的注释块。
- 第三方依赖全部声明在该块的 `dependencies = [...]` 中。
- 禁止创建虚拟环境、向仓库目录安装依赖、改写仓库结构。
- 禁止引入 `pyproject.toml`、`requirements*.txt`、`.venv` 等环境或打包文件。
- 运行方式固定：`uv run 文件名.py`。

## 模板

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
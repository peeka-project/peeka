# Peeka 开发指南（AI 编码代理专用）

基于 PEP 768 远程调试的 Python 3.8-3.14+ 运行时诊断工具。

## 构建与测试命令

本项目使用 **uv** 作为包管理器。所有 Python 命令必须加 `uv run` 前缀：

```bash
uv pip install -e .                 # 仅核心
uv pip install -e ".[tui]"         # 含 TUI（textual）
uv sync --dev                      # 开发依赖（pytest, textual, testcontainers, docker, pytest-cov, pytest-timeout）

uv run pytest tests/ -v                                          # 全部测试
uv run pytest tests/ -v -m "not e2e and not container"           # CI 安全（无需 ptrace/docker）
uv run pytest tests/test_injector.py -v                          # 单文件
uv run pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v  # 单测试
uv run pytest tests/e2e/ -v                                      # E2E（需要 ptrace）
uv run pytest tests/container/ -v -m container --timeout=180     # 容器测试（需要 Docker）
uv run ruff check peeka/                                         # Lint（无强制配置）
```

**规则**：所有 Python 命令（pytest、ruff、python 等）必须通过 `uv run <命令>` 执行，以使用项目虚拟环境。

Pytest 配置：`pytest.ini`（超时 60 秒，filterwarnings 忽略 DeprecationWarning）。

## 入口点

- `peeka-cli` → CLI（`peeka/cli/main.py`，argparse）
- `peeka` → TUI（`peeka/tui/__init__.py`，需要 textual）

## 代码风格

### 导入顺序：标准库 → 第三方 → 本地（组间空行，组内字母排序）

```python
import json
from typing import Any, Dict, Optional

import textual  # 第三方

from peeka.core.agent import PeekaAgent
```

`typing` 导入属于标准库组。循环导入使用 `TYPE_CHECKING` + 字符串注解。重型或低频模块可在方法内部导入。

### 类型注解与文档字符串

- 公开及非平凡函数签名**必须**添加类型注解；简单私有回调可省略
- 使用 `typing` 模块类型（`Dict`、`Optional`、`Any`、`Callable`），**不用** PEP 604 的 `X | None`（项目支持 Python 3.8+）
- 公开非平凡方法使用 Google 风格文档字符串（Args、Returns、Raises）
- 命名：类=PascalCase，函数=snake_case，私有=`_前缀`，常量=UPPER_SNAKE

### 错误处理（分层模式）

- **Core 模块**：抛出异常（如 `raise ValueError(...)`）
- **Commands**：捕获并返回 `{"status": "success"|"error", ...}` 字典
- **Agent**：包装命令执行，附加 traceback；吞掉异常以保证尽力恢复

### 线程安全与日志

共享可变状态使用 `threading.Lock`（agent/injector/TUI views）。临界区尽量短小。
TUI 流式视图通过双重检查锁惰性初始化客户端连接（`_ensure_stream_client()`）。

- **注入的 agent 代码**：`print("[peeka Agent] ...")` — 不用 logging 模块，最小化开销
- **CLI 输出**：`OutputFormatter`（`peeka/core/output.py`）结构化 JSONL
- **Commands/TUI views**：Python `logging` 模块

## 架构

```
peeka/
├── cli/main.py              # CLI 入口（argparse）
├── tui/
│   ├── app.py               # PeekaApp 主应用
│   ├── completion.py         # CLI/TUI 补全辅助
│   ├── screens/             # process_selector, main, help
│   ├── views/               # dashboard（含 agent log）, watch, stack,
│   │                        #   trace, monitor, memory, logger, inspect,
│   │                        #   thread, top
│   └── widgets/             # autocomplete_input
├── core/
│   ├── agent.py             # PeekaAgent - 注入目标进程，Unix socket 服务
│   ├── attach.py            # 进程附加（PEP 768 + GDB 回退）
│   ├── injector.py          # DecoratorInjector - 运行时函数包装
│   ├── client.py            # AgentClient, StreamingAgentClient
│   ├── observer.py          # ObservationManager
│   ├── monitor.py           # 性能监控
│   ├── output.py            # OutputFormatter（JSONL）
│   └── safeeval/            # 安全表达式求值（simpleeval）
├── commands/                # BaseCommand 子类
│   ├── base.py              # ABC: execute() + validate_params()
│   ├── watch.py, stack.py, trace.py, monitor.py, memory.py
│   ├── logger.py, search.py, reset.py, vmtool.py
│   ├── thread.py, top.py
│   └── complete.py, detach.py
└── utils/
    ├── formatters.py        # 值格式化工具
    └── patterns.py          # 模式匹配（通配符）
```

### 添加新命令

1. 创建 `peeka/commands/mycommand.py`，继承 `BaseCommand`
2. 实现 `execute(self, params: Dict[str, Any]) -> Dict[str, Any]`
3. 在 `PeekaAgent._COMMAND_REGISTRY`（`peeka/core/agent.py` 中的字典）注册 — 命令首次调度时通过 `_get_handler()` 惰性加载
4. 在 `peeka/cli/main.py` 添加 CLI 子命令
5. 在 `tests/test_mycommand.py` 编写测试

### 安全

**禁止对用户输入使用 `eval()`。** 必须使用 `peeka.core.safeeval.simpleeval.SimpleEval`。

## TUI 模式（Textual）

流式视图（watch、trace、stack、monitor）通过 `_ensure_stream_client()` 惰性创建独立的 `StreamingAgentClient` 连接（双重检查锁）。非流式视图（logger、memory、inspect、thread）共享主客户端。后台线程更新 UI 使用 `self.app.call_from_thread()`。

### TUI UI/UX 变更守则（减少返工）

当任务涉及布局、视觉层级、可用性（宽窄屏、焦点、分组）时，必须按以下顺序执行，避免“修一点坏一点”的反复提交：

1. **先冻结设计意图（Design Contract）**
   - 在动代码前，用 3-6 条可验证语句写清目标（例如：`140 列单行，80 列双行`、`A 区块左对齐，B 区块右对齐`、`Stats 与 Tree 必须是两个独立 panel`）。
   - 若意图未冻结，不允许直接改 TCSS。

2. **区分“结构变更”和“皮肤变更”**
   - 结构变更：`compose()` 层级、panel 拆分/合并、focus 链、tab 可达性。
   - 皮肤变更：颜色、边框样式、间距、字号。
   - 先做结构再做皮肤；禁止在一个小提交中交替改二者。

3. **必须补“几何断言”测试，而不只看 class**
   - 除 class 断言外，至少补 1 条 region 断言（`x/y/width/height`）覆盖目标约束。
   - 宽窄屏至少各测一个尺寸（推荐 `80x24` 和 `140x24`）。
   - 涉及键盘可达性必须测 `tab` 焦点链。

4. **提交前执行最小验证矩阵**
   - `uv run ruff check <changed files>`
   - `uv run pytest tests/tui/test_style_layout.py -k "<affected views>" -v`
   - 若有焦点行为变更，额外跑对应 view 的焦点测试。

5. **提交粒度规则**
   - 一个提交只表达一个意图（例如：`memory 顶栏响应式`）。
   - 微小修补（文案、阈值、空格）应优先并入最近相关提交，避免连续“补丁型提交”。

### TUI 变更 DoD（Definition of Done）

涉及 UI/UX 的任务在满足以下条件前不得声明完成：

- 设计意图 3-6 条全部可映射到代码和测试。
- 至少 1 条宽屏几何断言 + 1 条窄屏几何断言。
- 如果是 panel 拆分任务，必须验证“独立 panel + 间距 + 对齐”三项。
- 如果是可交互区域任务，必须验证“可聚焦 + Tab 可达”。
- 变更说明中明确“保持不变”的行为（防止隐式回归）。

## 测试模式

大多数测试使用**基于类**的 pytest 测试加 fixture。使用自定义 `MockAgent` / `MockStreamingAgentClient`（不用 unittest.mock）。动态测试模块插入 `sys.modules`，teardown 时清理。

### 测试标记（在 pytest.ini 中声明）

| 标记          | 含义                      | 用途                                         |
|---------------|---------------------------|----------------------------------------------|
| `tui`         | 需要 textual              | 大量用于 `tests/tui/`                        |
| `unit`        | 快速，无外部依赖          | 少量使用                                     |
| `integration` | 进程内 agent/client       | 集成测试                                     |
| `e2e`         | 需要 ptrace               | 按目录（`tests/e2e/`）+ conftest             |
| `container`   | 需要 Docker               | 按目录（`tests/container/`）+ conftest       |
| `slow`        | 慢测试（>10s）            | —                                            |
| `py314`       | 需要 Python 3.14+         | —                                            |
| `gdb`         | 需要 GDB                  | —                                            |

### 关键测试 Fixture

- `tests/tui/conftest.py` — `MockStreamingAgentClient`，共享 TUI 测试 mock
- `tests/e2e/conftest.py` — `has_ptrace_permission`、`has_pep768`、`has_gdb`、`target_process`
- `tests/container/conftest.py` — `gdb_container`、`py314_container`、`container_target`

## Python 版本支持

| 版本     | 附加机制                  | 要求                              |
|----------|---------------------------|-----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | 无                                |
| 3.8-3.13 | GDB + ptrace 回退         | GDB、python3-dbg、CAP_SYS_PTRACE |

CI 测试覆盖 Python 3.9、3.12 和 3.14。

## Docker 测试镜像

`docker/` 下有三个测试镜像，用于 testcontainers 和手动验证。均需 `--cap-add=SYS_PTRACE`。

| 镜像 | Dockerfile | Python | 用途 |
|-------|------------|--------|---------|
| `peeka-test:3.8`  | `test.Dockerfile-3.8`  | 3.8  | GDB + ptrace 附加测试 |
| `peeka-test:3.12` | `test.Dockerfile-3.12` | 3.12 | GDB + ptrace 附加测试 |
| `peeka-test:3.14` | `test.Dockerfile-3.14` | 3.14 | PEP 768 原生附加测试 |

构建使用 `--network=host`（代理路由）。运行：`uv run pytest tests/container/test_attach.py -v -m container --timeout=180`

## Git 规范

- **提交风格**：语义化（`feat:`、`fix:`、`perf:`、`docs:`、`test:`、`refactor:`、`chore:`）
- **范围**：括号内模块名 — `fix(tui):`、`feat(cli):`、`test(tui):`、`fix(core):`
- **语言**：英文
- **每完成一个任务就提交**：禁止留下未暂存的修改。
- **临时文件**：测试时临时文件必须写到系统临时目录（`tempfile.gettempdir()`），不要写到项目根目录。

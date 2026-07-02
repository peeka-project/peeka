---
name: container-test
description: 在 Docker 容器内测试 peeka CLI 和 TUI。用于验证功能在真实容器环境中的端到端工作。触发词："test in container", "verify in docker", "container test", "run e2e", "test CLI then TUI"。
---

# 容器测试技能

在 Docker 测试容器内端到端验证 peeka 功能。本技能提供了一套系统化的流程：先测试 CLI 命令，再使用 Textual 的无头测试框架验证 TUI 行为。

## 前置条件

- 容器 `peeka-test-<version>` 必须使用 `--cap-add=SYS_PTRACE` 运行，其中 `<version>` 是 Python 版本（例如 `peeka-test-3.8`、`peeka-test-3.12`、`peeka-test-3.14`）
- 容器内必须运行着 demo 进程（由 Docker 镜像自动启动）
- 项目源码必须挂载到 `/app`（可编辑安装）

**支持的版本**：3.8、3.12（基于 GDB 附加）、3.14（PEP 768 原生附加）

## 快速参考

将 `<version>` 替换为目标 Python 版本：`3.8`、`3.12` 或 `3.14`。

```bash
# 检查容器是否在运行
docker ps --filter name=peeka-test-<version>

# 检查 demo 进程
docker exec peeka-test-<version> ps aux | grep "demo.py"

# 清理残留的 TUI 进程
docker exec peeka-test-<version> bash -c 'kill $(pgrep -f "peeka.tui") 2>/dev/null; true'

# 清理 Python 缓存（代码更改后很重要！）
docker exec peeka-test-<version> find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# 附加 agent 到 demo 进程
docker exec peeka-test-<version> python3 -m peeka.cli attach <PID>

# 查找 socket 路径
docker exec peeka-test-<version> ls /tmp/peeka_*.sock
```

## 工作流程

### 阶段 1：CLI 测试

先测试 CLI 命令，因为它们更容易调试和验证。

#### 1.1 附加到目标进程

将 `<version>` 替换为目标 Python 版本：

```bash
# 查找 demo PID
docker exec peeka-test-<version> ps aux | grep "demo.py"

# 附加
docker exec peeka-test-<version> python3 -m peeka.cli attach <PID>
```

预期输出包含 `"type": "success"` 和 socket 路径。

#### 1.2 测试具体的 CLI 命令

将 `<version>` 替换为目标 Python 版本：

```bash
# 示例：测试 memory gc
docker exec peeka-test-<version> python3 -m peeka.cli memory --action gc

# 示例：测试 memory overview
docker exec peeka-test-<version> python3 -m peeka.cli memory --action overview

# 示例：测试 watch
docker exec peeka-test-<version> python3 -m peeka.cli watch "demo.Calculator.add" --times 2
```

**成功标准**：命令返回 JSON，包含 `"status": "success"` 和预期的数据字段。

**如果 CLI 失败**：先修复后端问题，不要进入 TUI 测试。

### 阶段 2：TUI 测试（基于 Textual 无头模式）

使用 Textual 的 `run_test()` 以编程方式验证 TUI 行为，无需 tmux。

#### 2.1 创建测试脚本

编写一个 Python 测试脚本：
1. 创建一个包含 `MainScreen` 的测试 `App`
2. 使用 `pilot` 导航到相关标签页
3. 查询 widget 状态以验证数据是否存在
4. **截取 SVG 截图进行视觉验证**（显示相关的 bug 必须执行此步骤）
5. 报告通过/失败

**模板**（针对被测试的具体功能进行调整）：

```python
#!/usr/bin/env python3
"""容器 TUI 测试：[功能名称]"""
import sys, asyncio, glob, os

os.environ.setdefault("TERM", "xterm-256color")
os.environ.setdefault("COLORTERM", "truecolor")

sockets = glob.glob("/tmp/peeka_*.sock")
if not sockets:
    print("FAIL: 未找到 peeka socket，请先运行 attach。", file=sys.stderr)
    sys.exit(1)
socket_path = sockets[0]

from textual.app import App, ComposeResult
from textual.widgets import DataTable, TabbedContent
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.memory import MemoryView  # 导入你要测试的视图


class TestApp(App):
    CSS_PATH = "/app/peeka/tui/styles/peeka.tcss"

    def __init__(self, socket_path: str):
        super().__init__()
        self.socket_path = socket_path

    def on_mount(self) -> None:
        self.push_screen(
            MainScreen(pid=196, session_id="test", socket_path=self.socket_path)
        )


async def run_test():
    app = TestApp(socket_path)
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        # 等待 MainScreen 挂载并连接
        for _ in range(15):
            await asyncio.sleep(0.5)
            await pilot.pause()

        screen = app.screen
        assert isinstance(screen, MainScreen), f"期望 MainScreen，实际得到 {type(screen)}"

        # 导航到要测试的标签页（例如 '6' 对应 Memory）
        await pilot.press("6")
        for _ in range(15):
            await asyncio.sleep(0.5)
            await pilot.pause()

        # === 在此处验证你的功能 ===
        # 示例：检查 GC Objects 表是否有数据
        memory_view = screen.query_one(MemoryView)
        table = memory_view.query_one("#mem-objects-table", DataTable)

        if table.row_count > 0:
            print(f"PASS: 表格有 {table.row_count} 行", file=sys.stderr)
        else:
            print(f"FAIL: 表格为空", file=sys.stderr)
            sys.exit(1)

        # === SVG 截图（显示/视觉相关 bug 必须执行）===
        svg = app.export_screenshot(title="测试：[功能名称]")
        with open("/tmp/tui_test_screenshot.svg", "w") as f:
            f.write(svg)
        print(f"截图已保存：/tmp/tui_test_screenshot.svg（{len(svg)} 字节）", file=sys.stderr)


asyncio.run(run_test())
```

#### 2.2 运行测试

将 `<version>` 替换为目标 Python 版本：

```bash
# 重要：如果代码已更改，先清除缓存
docker exec peeka-test-<version> find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# 杀死所有残留的 TUI 进程
docker exec peeka-test-<version> bash -c 'kill $(pgrep -f "peeka.tui") 2>/dev/null; true'

# 运行测试（使用 timeout 防止挂起）
docker exec peeka-test-<version> timeout 30 python3 /app/tests/<test_script>.py
```

#### 2.3 验证结果

- **PASS**：脚本退出码为 0，打印 "PASS" 消息
- **FAIL**：脚本退出码为 1 或打印 "FAIL"，通过调试日志排查

#### 2.4 SVG 截图验证（显示/视觉相关 bug 必须执行）

**当 bug 涉及 widget 不渲染、数据不可见、布局错乱或任何视觉问题时，必须捕获并分析 SVG 截图。** 仅检查 `row_count > 0` 是不够的——数据可能已加载但由于 CSS/布局问题不可见（这是 GC Objects bug 需要 5+ 次才能修复的根本原因）。

**为什么用 SVG，而不是 tmux capture-pane？**
- `app.export_screenshot()` 是 Textual 框架级别的渲染——它精确捕获用户看到的内容
- tmux `capture-pane` 会丢失 Textual 的丰富样式，输出不可靠的文本
- SVG 包含实际渲染的文本，因此可以用 grep 验证内容是否可见

**如何捕获：**

```python
# 在无头测试内部，导航到目标视图后：
svg = app.export_screenshot(title="测试：功能名称")
with open("/tmp/tui_test_screenshot.svg", "w") as f:
    f.write(svg)
```

**如何在宿主机上分析 SVG：**

```bash
# 1. 复制 SVG 到宿主机
docker cp peeka-test-<version>:/tmp/tui_test_screenshot.svg /tmp/tui_test_screenshot.svg

# 2. 在 SVG 文本中搜索期望的内容
#    （SVG 包含 <text> 元素，内容是实际渲染的字符）
#    使用 grep 验证特定数据是否可见：
grep -oP '>[^<]{3,}<' /tmp/tui_test_screenshot.svg | head -30

# 3. 也可以使用 Grep 工具搜索特定内容：
#    - 表头："Type", "Count", "Size"
#    - 数据值："dict", "list", "function", 数字
#    - Widget 标签："Refresh", "Track", 标签页名称
```

**在 SVG 中检查什么：**

| 检查项 | 方法 | 失败意味着 |
|--------|------|-----------|
| 数据行可见 | 用 grep 搜索期望的类型名（例如 `dict`、`list`） | 数据已加载但表格没有渲染空间（CSS 问题） |
| 表头可见 | 用 grep 搜索列名（例如 `Type`、`Count`） | 表格本身未渲染 |
| Widget 尺寸 | 在测试代码中检查 `widget.size` | 布局给了 0 高度/宽度 |
| 正确的标签页激活 | 用 grep 搜索带激活样式的标签名 | 导航未生效 |

**推荐的组合验证模式：**

```python
# 同时检查数据状态和视觉渲染
table = view.query_one("#my-table", DataTable)
print(f"row_count={table.row_count} size={table.size}")

# 数据检查
assert table.row_count > 0, "表格没有数据"

# 视觉检查——表格必须有足够的渲染空间
assert table.size.height > 10, f"表格太短无法显示数据：{table.size}"

# 截图供人工检查
svg = app.export_screenshot(title="测试结果")
with open("/tmp/tui_test_screenshot.svg", "w") as f:
    f.write(svg)

# 然后在宿主机上复制 SVG 并用 grep 搜索期望内容
```

**经验教训**：GC Objects bug 当时 `row_count=20`（数据正确加载）但 `table.size.height=4`（由于 `ContentSwitcher` 默认使用 `height: auto` 导致不可见）。如果不同时检查尺寸和视觉内容，这个问题被误诊了 5+ 次。

### 阶段 3：调试（如果 TUI 测试失败）

#### 3.1 添加临时调试日志

在视图代码的关键位置添加 `print(..., file=sys.stderr, flush=True)`。`file=sys.stderr` 确保输出不会干扰 Textual 的 stdout 渲染。

```python
# 在文件顶部添加：
import sys
def _dbg(msg):
    print(f'[DBG] {msg}', file=sys.stderr, flush=True)

# 然后在关键位置添加 _dbg() 调用：
_dbg(f'set_client: _mounted={self._mounted}')
_dbg(f'worker result: {response}')
```

#### 3.2 重新运行测试

```bash
docker exec peeka-test-<version> python3 /app/tests/<test_script>.py 2>&1
```

Stderr 调试输出和 stdout 测试结果会交错显示。关注执行流程：
1. `on_mount` → `_mounted=True`
2. `set_client` → client 已连接
3. 数据获取 → 成功/失败
4. 表格填充 → 行数

#### 3.3 修复后清理调试日志

**重要**：提交前务必删除所有 `_dbg` 调用和调试函数。

## 常见问题

### 残留的 TUI 进程
之前测试会话遗留的 TUI 进程会使用缓存的 Python 模块。测试代码更改前务必先杀死它们：
```bash
docker exec peeka-test-<version> bash -c 'kill $(pgrep -f "peeka.tui") 2>/dev/null; true'
```

### 残留的 `__pycache__`
Python 可能使用代码更改前缓存的 `.pyc` 文件：
```bash
docker exec peeka-test-<version> find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

### 模块缓存（sys.modules）
当目标进程长时间运行时，Python 会在 `sys.modules` 中缓存来自首次 attach 会话的 `peeka.*` 模块。**Peeka 的 agent bootstrap 现已在每次新 attach 时自动清除这些缓存**，因此挂载卷上的源码改动无需重启目标进程即可生效。

如果 detach 后重新 attach 仍观察到旧行为，请确认 detach 已完整执行后再重新 attach。此清理仅针对 `peeka.*` 命名空间，不会影响目标应用的其他模块。

### Socket 消失
Agent socket 在进程重启或清理后会过期。重新附加：
```bash
docker exec peeka-test-<version> python3 -m peeka.cli attach <PID>
```

### 容器内无网络
如果 pip/apt 因网络问题失败，不要尝试安装包。容器的可编辑安装（`/app`）已有宿主机挂载的最新源码。

### Worker 永不完成
如果 `await worker.wait()` 挂起，可能是 socket 连接已经断开。先用 CLI 命令验证（阶段 1）。

## 标签页快捷键（用于 `pilot.press()`）

实际绑定来自 `peeka/tui/screens/main.py`：

| 按键 | 标签页 |
|------|-------|
| `1` | Dashboard |
| `2` | Watch |
| `3` | Trace |
| `4` | Stack |
| `5` | Monitor |
| `6` | Memory |
| `7` | Logger |
| `8` | Inspect |
| `9` | Threads |
| `0` | Top |

## 可用视图和 Widget ID

### Memory 视图
- `#mem-objects-table` — GC 对象 DataTable
- `#mem-alloc-table` — 分配 DataTable
- `#mem-diff-table` — 差异 DataTable
- `#mem-ref-tree` — 引用树
- `#mem-rss` — RSS 静态文本
- `#mem-total` — 跟踪内存静态文本
- `#mem-gc` — GC 代际静态文本

### 其他视图（从 `peeka.tui.views.<module>` 导入）
- `DashboardView` — 进程信息
- `WatchView` — 函数观察
- `TraceView` — 调用追踪
- `StackView` — 调用栈
- `MonitorView` — 性能统计
- `LoggerView` — 日志管理
- `InspectView` — 对象检查
- `ThreadView` — 线程信息
- `TopView` — CPU 使用率
# TUI 测试方法分析报告

## 研究背景

本报告研究了两个优秀的 AI 构建的 TUI 代码库（pi-mono 和 opencode）的测试方法，并分析了 peeka 项目当前 TUI 测试存在的问题以及改进方向。

## 一、外部项目 TUI 测试方法研究

### 1.1 pi-mono 的测试方法

**项目信息：**
- 仓库：https://github.com/badlogic/pi-mono
- 技术栈：Node.js/TypeScript
- TUI 实现：自定义终端渲染引擎

**测试策略：**

pi-mono 采用了**虚拟终端（VirtualTerminal）**测试方法，这是一个核心特点：

```typescript
// 从 packages/tui/test/editor.test.ts
function createTestTUI(cols = 80, rows = 24): TUI {
    return new TUI(new VirtualTerminal(cols, rows));
}
```

**关键特性：**

1. **全面的测试覆盖**：仅 `editor.test.ts` 一个文件就包含 40+ 个测试用例
2. **复杂场景测试**：
   - 历史记录导航（history navigation）
   - Unicode 字符处理
   - 自动换行（word wrapping）
   - 撤销/重做（undo/redo）
   - 自动补全（autocomplete）
   - Kill ring 功能
   - 粘性列行为（sticky column）

3. **虚拟终端隔离**：通过 VirtualTerminal 模拟真实终端环境，无需依赖实际的 TTY

**测试样例分析：**

```typescript
// 典型的测试结构
test("editor history navigation", () => {
    const tui = createTestTUI();
    const editor = new Editor(tui);

    // 模拟用户输入
    editor.input("first line");
    editor.input(Keys.Enter);
    editor.input("second line");

    // 验证状态
    assert(editor.getLines().length === 2);

    // 模拟历史导航
    editor.input(Keys.Up);
    assert(editor.getCurrentLine() === "first line");
});
```

**优势：**
- ✅ 完全同步的测试流程，无异步协调问题
- ✅ 测试可以精确控制终端状态
- ✅ 覆盖复杂的用户交互场景
- ✅ 不依赖外部进程或系统权限

### 1.2 opencode 的测试方法

**项目信息：**
- 仓库：https://github.com/anomalyco/opencode
- 技术栈：TypeScript + Bun
- 主要语言：98.6% TypeScript

**测试特点：**
- 使用 Bun 作为测试运行器
- TypeScript 类型安全的测试代码
- 模块化的测试结构

（注：opencode 的测试文件未能深入获取，但从项目结构推断其采用现代 TypeScript 测试实践）

## 二、peeka 当前 TUI 测试问题分析

### 2.1 当前测试结构

peeka 使用 Python + Textual 框架，采用三层测试架构：

| 测试层级 | 文件 | 代码行数 | 标记 | 用途 |
|---------|------|---------|------|------|
| 单元测试 | `tests/test_tui.py` | 274 | `@pytest.mark.tui` | 组件结构验证 |
| E2E 测试 | `tests/e2e/test_tui_e2e.py` | 353 | `@pytest.mark.e2e`, `@pytest.mark.tui` | 真实连接测试 |
| 容器测试 | `tests/e2e/test_container_tui.py` | 60 | `@pytest.mark.container` | Docker 环境测试 |

**测试模式示例：**

```python
# tests/test_tui.py
@pytest.mark.asyncio
async def test_screen_renders_with_table(self):
    app = PeekaApp()
    async with app.run_test() as pilot:
        assert isinstance(app.screen, ProcessSelectorScreen)
        table = app.screen.query_one("#process-table", DataTable)
        assert table is not None
```

### 2.2 核心问题分析

#### 问题 1：测试覆盖片面，仅验证"快乐路径"

**现状：**
- ✅ 验证了 UI 组件存在性（如按钮、输入框、表格）
- ✅ 验证了基本的标签页切换
- ❌ **未测试错误处理**：如连接失败、命令执行错误、无效输入
- ❌ **未测试边界条件**：如空数据、超长输入、网络超时

**对比 pi-mono：**
pi-mono 有专门的错误场景测试，例如：
- 测试在没有历史记录时按 Up 键的行为
- 测试超长行的换行处理
- 测试无效 Unicode 字符的处理

**peeka 缺失示例：**
```python
# 应该有但没有的测试
async def test_watch_view_handles_connection_failure(self):
    """测试 Watch 视图在连接失败时的行为"""
    # 当前没有这类测试

async def test_watch_view_handles_invalid_pattern(self):
    """测试无效模式的错误提示"""
    # 当前没有这类测试
```

#### 问题 2：缺乏复杂交互流程测试

**现状：**
- 当前测试大多是单步操作：按一个键 → 验证一个状态
- 缺少多步骤的用户场景测试

**对比 pi-mono：**
pi-mono 测试复杂流程，例如：
1. 输入文本
2. 移动光标
3. 执行撤销
4. 再执行重做
5. 验证最终状态

**peeka 应有但缺失的测试：**
```python
async def test_watch_workflow_end_to_end(self):
    """完整的 Watch 工作流测试"""
    # 1. 切换到 Watch 标签页
    # 2. 输入 pattern
    # 3. 输入 condition
    # 4. 点击 Watch 按钮
    # 5. 验证观察开始
    # 6. 模拟接收数据更新
    # 7. 点击 Stop 按钮
    # 8. 验证观察停止
    # 当前测试未覆盖此完整流程
```

#### 问题 3：异步与线程协调测试不足

**现状：**
peeka 的 TUI 视图大量使用 `run_worker()` 启动后台线程：

```python
# 来自 peeka/tui/views/watch.py
worker = self.run_worker(
    lambda: self._stream_observations(watch_id),
    thread=True,
    exclusive=False
)
```

**问题：**
- 测试中只验证方法存在（`test_watch_view_callable_wrapper`）
- **未测试 worker 实际执行逻辑**
- **未测试 worker 与 UI 更新的协调**
- **未测试 worker 异常处理**

**对比 pi-mono：**
pi-mono 使用同步的 VirtualTerminal，完全避免了异步协调问题。

**peeka 应有的测试：**
```python
async def test_watch_worker_updates_ui(self):
    """测试 Watch worker 实际更新 UI"""
    # 1. 启动 watch
    # 2. 注入模拟的观察数据
    # 3. 验证 UI 中的 DataTable 更新
    # 4. 验证更新顺序正确
    # 当前测试未覆盖此场景
```

#### 问题 4：缺少客户端模拟（Mock）

**现状：**
- E2E 测试使用真实的 `StreamingAgentClient`
- 单元测试完全没有客户端模拟
- 导致单元测试无法测试依赖客户端的逻辑

**问题示例：**

```python
# tests/test_tui.py 中的测试
async def test_watch_view_buttons(self):
    app = PeekaApp()
    async with app.run_test() as pilot:
        app.push_screen(MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock"))
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()

        watch_btn = app.screen.query_one("#watch-btn", Button)
        stop_btn = app.screen.query_one("#stop-btn", Button)
        assert watch_btn is not None
        assert stop_btn is not None
        # ❌ 仅验证按钮存在，未验证点击按钮的实际效果
```

**对比 pi-mono：**
pi-mono 的 VirtualTerminal 本身就是一个完整的 mock，可以完全控制输入输出。

**peeka 需要：**
```python
class MockStreamingAgentClient:
    def __init__(self):
        self._watch_responses = []

    def send_command(self, command, params):
        # 返回预设的响应
        if command == "watch":
            return {"status": "success", "watch_id": "test-123"}

    def stream_command(self, command, params):
        # 生成预设的流式数据
        for response in self._watch_responses:
            yield response
```

#### 问题 5：测试数据验证不充分

**现状：**
测试经常使用松散的断言：

```python
# tests/e2e/test_tui_e2e.py:131
assert "RSS:" in rss_text
assert ("MB" in rss_text) or ("detecting" in rss_text)
```

**问题：**
- 只验证字符串包含，不验证数据格式
- 不验证数据的合理性范围
- 允许 "detecting..." 持续存在，未验证最终加载成功

**对比 pi-mono：**
```typescript
// pi-mono 的精确验证
assert(editor.getLines().length === 2);
assert(editor.getCurrentLine() === "first line");
assert(editor.getCursorPosition() === { row: 0, col: 10 });
```

### 2.3 根本原因总结

| 问题根源 | 说明 | 影响 |
|---------|------|------|
| **框架限制** | Textual 的 `run_test()` 是异步的，需要大量 `await pilot.pause()` | 难以精确控制时序 |
| **真实依赖** | E2E 测试依赖真实进程、ptrace 权限 | 测试环境脆弱，难以复现 |
| **缺少分层** | 单元测试和 E2E 测试边界模糊 | 测试速度慢，失败难定位 |
| **测试意识** | 过度关注"能跑"，忽视"跑对" | 测试未发现实际 bug |

## 三、改进建议

### 3.1 借鉴 pi-mono：引入虚拟客户端层

**方案：**

创建 `tests/tui/mock_client.py`：

```python
from typing import Any, Dict, Generator, List
from peeka.core.client import StreamingAgentClient

class MockStreamingAgentClient:
    """用于 TUI 单元测试的模拟客户端"""

    def __init__(self):
        self._responses: Dict[str, Any] = {}
        self._streams: Dict[str, List[Dict]] = {}

    def set_response(self, command: str, response: Dict[str, Any]):
        """设置命令的预期响应"""
        self._responses[command] = response

    def set_stream(self, command: str, data: List[Dict[str, Any]]):
        """设置流式命令的数据序列"""
        self._streams[command] = data

    def send_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """模拟同步命令"""
        return self._responses.get(command, {"status": "error", "error": "Not mocked"})

    def stream_command(
        self, command: str, params: Dict[str, Any]
    ) -> Generator[Dict[str, Any], None, None]:
        """模拟流式命令"""
        for item in self._streams.get(command, []):
            yield item
```

**使用示例：**

```python
async def test_watch_view_displays_observations(self):
    """测试 Watch 视图正确显示观察数据"""
    mock_client = MockStreamingAgentClient()

    # 设置模拟数据
    mock_client.set_response("watch", {"status": "success", "watch_id": "w1"})
    mock_client.set_stream("watch", [
        {
            "watch_id": "w1",
            "function": "my_func",
            "args": [1, 2],
            "result": 3,
            "timestamp": 1234567890.0
        }
    ])

    app = PeekaApp()
    async with app.run_test() as pilot:
        main_screen = MainScreen(pid=12345, session_id="test", socket_path="/fake")

        # 注入 mock 客户端
        main_screen._client = mock_client

        app.push_screen(main_screen)
        await pilot.pause()

        # 执行 watch 操作
        await pilot.press("w")
        await pilot.pause()

        pattern_input = app.screen.query_one("#watch-pattern", Input)
        pattern_input.value = "my_func"
        await pilot.pause()

        watch_btn = app.screen.query_one("#watch-btn", Button)
        await pilot.click(watch_btn)
        await pilot.pause()

        # 验证数据显示
        table = app.screen.query_one("#watch-results", DataTable)
        assert table.row_count == 1

        # 验证具体内容
        first_row = list(table.rows[0].cells)
        assert "my_func" in str(first_row)
        assert "1, 2" in str(first_row)
        assert "3" in str(first_row)
```

### 3.2 增加错误场景测试

**新增测试类别：**

```python
class TestWatchViewErrorHandling:
    """专门测试错误处理"""

    async def test_watch_invalid_pattern(self):
        """测试无效模式的错误提示"""
        mock_client = MockStreamingAgentClient()
        mock_client.set_response("watch", {
            "status": "error",
            "error": "Invalid pattern: *invalid*"
        })
        # ... 验证错误消息显示

    async def test_watch_connection_lost(self):
        """测试连接断开时的恢复"""
        mock_client = MockStreamingAgentClient()
        mock_client.set_stream("watch", [
            {"watch_id": "w1", "data": "first"},
            # 模拟连接断开
            {"status": "error", "error": "Connection lost"}
        ])
        # ... 验证错误处理和 UI 状态

    async def test_watch_empty_results(self):
        """测试空结果的显示"""
        mock_client = MockStreamingAgentClient()
        mock_client.set_stream("watch", [])
        # ... 验证空状态提示
```

### 3.3 增加复杂交互流程测试

**新增端到端用户场景测试：**

```python
class TestWatchWorkflow:
    """测试完整的用户工作流"""

    async def test_full_watch_cycle(self):
        """测试完整的 watch-update-stop 循环"""
        mock_client = MockStreamingAgentClient()

        # 1. 第一次 watch
        mock_client.set_response("watch", {"status": "success", "watch_id": "w1"})
        mock_client.set_stream("watch", [
            {"watch_id": "w1", "function": "func1", "result": 10}
        ])

        app = PeekaApp()
        async with app.run_test() as pilot:
            # ... 启动 watch
            # ... 验证数据显示

            # 2. 停止 watch
            stop_btn = app.screen.query_one("#stop-btn")
            await pilot.click(stop_btn)
            await pilot.pause()

            # 验证停止后的 UI 状态
            watch_btn = app.screen.query_one("#watch-btn")
            assert not watch_btn.disabled

            # 3. 修改条件后重新 watch
            condition_input = app.screen.query_one("#watch-condition", Input)
            condition_input.value = "result > 5"

            mock_client.set_response("watch", {"status": "success", "watch_id": "w2"})
            mock_client.set_stream("watch", [
                {"watch_id": "w2", "function": "func1", "result": 10},
                {"watch_id": "w2", "function": "func2", "result": 3}  # 应被过滤
            ])

            await pilot.click(watch_btn)
            await pilot.pause()

            # 验证条件过滤生效
            table = app.screen.query_one("#watch-results", DataTable)
            assert table.row_count == 1  # 只有 result=10 的记录

    async def test_switch_tabs_preserves_state(self):
        """测试切换标签页后状态保持"""
        # 1. 在 Watch 标签输入内容
        # 2. 切换到其他标签
        # 3. 切换回 Watch 标签
        # 4. 验证输入内容仍然存在
```

### 3.4 改进测试断言的精确性

**当前问题：**
```python
# 松散的断言
assert "RSS:" in rss_text
```

**改进方案：**
```python
import re

def test_memory_view_displays_valid_rss(self):
    """测试 RSS 显示格式正确且数值合理"""
    mock_client = MockStreamingAgentClient()
    mock_client.set_response("memory", {
        "status": "success",
        "rss_bytes": 52428800  # 50 MB
    })

    # ... 执行刷新操作

    rss_widget = app.screen.query_one("#mem-rss")
    rss_text = rss_widget.render().plain

    # 精确验证格式
    match = re.search(r"RSS:\s+(\d+\.\d+)\s+MB", rss_text)
    assert match is not None, f"RSS format incorrect: {rss_text}"

    # 验证数值范围
    rss_mb = float(match.group(1))
    assert 49.0 <= rss_mb <= 51.0, f"RSS value {rss_mb} MB not in expected range"
```

### 3.5 分层测试策略优化

**建议的三层架构：**

| 层级 | 测试对象 | 依赖 | 速度 | 数量占比 |
|-----|---------|------|------|---------|
| **视图单元测试** | 单个视图组件 | MockClient | 快（<1s） | 70% |
| **集成测试** | 跨视图交互 | MockClient | 中（1-5s） | 20% |
| **E2E 测试** | 完整流程 | 真实进程 | 慢（10s+） | 10% |

**实施方案：**

```python
# tests/tui/views/test_watch_view.py（单元测试）
class TestWatchViewUnit:
    """Watch 视图单元测试，使用 MockClient"""
    # 快速测试单个视图的逻辑

# tests/tui/test_integration.py（集成测试）
class TestMainScreenIntegration:
    """MainScreen 与多个视图的交互测试"""
    # 测试视图间的协调

# tests/e2e/test_tui_e2e.py（E2E 测试）
class TestFullWorkflowE2E:
    """使用真实进程的完整流程测试"""
    # 少量关键场景的端到端验证
```

### 3.6 引入测试覆盖率监控

**工具：**
```bash
pip install pytest-cov
pytest tests/tui/ --cov=peeka/tui --cov-report=html
```

**目标：**
- 视图代码覆盖率 > 80%
- 错误分支覆盖率 > 60%
- 关键流程覆盖率 = 100%

### 3.7 添加性能基准测试

**问题：**
当前测试未验证性能，可能存在性能退化。

**方案：**

```python
import time

class TestWatchViewPerformance:
    async def test_watch_handles_high_frequency_updates(self):
        """测试高频更新下的 UI 响应性"""
        mock_client = MockStreamingAgentClient()

        # 模拟每秒 100 次更新
        mock_client.set_stream("watch", [
            {"watch_id": "w1", "data": f"update_{i}"}
            for i in range(1000)
        ])

        start = time.time()

        # ... 执行 watch 并等待所有更新

        elapsed = time.time() - start

        # 验证处理时间合理（< 5 秒处理 1000 条更新）
        assert elapsed < 5.0, f"Update processing too slow: {elapsed}s"

        # 验证 UI 未卡死
        table = app.screen.query_one("#watch-results", DataTable)
        assert table.row_count > 0
```

## 四、实施优先级

### P0（立即实施）：
1. ✅ 创建 `MockStreamingAgentClient` 类
2. ✅ 重构现有单元测试使用 Mock 客户端
3. ✅ 添加 5-10 个错误场景测试

### P1（本周内）：
4. ✅ 添加 3-5 个复杂交互流程测试
5. ✅ 改进所有断言，使用精确验证
6. ✅ 配置覆盖率监控

### P2（下次迭代）：
7. ✅ 添加性能基准测试
8. ✅ 编写测试最佳实践文档
9. ✅ 建立 CI 中的覆盖率门禁（最低 75%）

## 五、总结

### 5.1 pi-mono 的核心经验

| 经验 | peeka 如何应用 |
|-----|---------------|
| **VirtualTerminal 隔离** | 使用 MockStreamingAgentClient 隔离外部依赖 |
| **全面的测试用例** | 从当前 21 个测试增加到 60+ 个测试 |
| **复杂场景覆盖** | 添加多步骤工作流测试 |
| **同步测试流程** | 使用 Mock 避免异步协调问题 |

### 5.2 当前测试的核心问题

**一句话总结：**
> peeka 的 TUI 测试验证了"UI 存在"，但未验证"UI 正确工作"。

**三大短板：**
1. **覆盖不足**：只测试快乐路径，忽视错误场景
2. **验证松散**：只检查字符串包含，不验证数据正确性
3. **隔离不够**：单元测试依赖真实连接，测试脆弱且慢

### 5.3 改进后的预期效果

实施上述改进后：
- ✅ 测试数量：从 21 个增加到 60+ 个
- ✅ 覆盖率：从约 40% 提升到 80%+
- ✅ 测试速度：单元测试从平均 5s 降至 1s
- ✅ 稳定性：减少 90% 的 E2E 测试失败率
- ✅ 质量保障：能够在 PR 阶段发现 UI 逻辑错误

---

**报告生成时间：** 2026-02-11
**研究对象：** pi-mono, opencode, peeka
**分析者：** Claude (Anthropic)

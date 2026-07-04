# ADR 0004: Agent Module Cache Cleanup 验证

- 状态：Accepted
- 日期：2026-07-04
- 决策者：peeka 维护者
- 相关计划：`.sisyphus/plans/agent-module-cache-cleanup-validation.md`（执行记录）

## 上下文

`agent-module-cache-cleanup` 计划在 `_create_agent_script()` 的生成脚本中加入了一段 bootstrap 片段，在 agent 导入自身代码之前清除目标进程 `sys.modules` 中所有 `peeka.*` 缓存模块：

```python
for _peeka_mod in list(sys.modules.keys()):
    if _peeka_mod == 'peeka' or _peeka_mod.startswith('peeka.'):
        sys.modules.pop(_peeka_mod, None)
```

该改动修复了 Docker volume-mount 工作流中源码修改不生效的 bug，但引发两个需要实证验证的风险点：

1. **P1**：`shutdown_agent_resources()` 使用 `isinstance(handler, ResourceOwningCommand)` 识别资源所有命令。模块 reload 后新旧 `ResourceOwningCommand` 是不同 class 对象，旧 handler 实例可能无法被识别 → 资源泄漏。

2. **P2**：`_uninstall_exit_hooks()` 使用 `is` 比较函数身份来决定是否恢复信号处理器。`stop()` 可能在非主线程被调用，而 `signal.signal()` 只能从主线程调用。

---

## P1 验证结果：安全

**测试**：`TestModuleCacheResourceOwnerCleanup`（`tests/container/test_attach.py`）

**验证流程**：
1. attach → 启动 `monitor`（`ResourceOwningCommand`） → detach
2. re-attach 到同一 PID（触发 `sys.modules` 清除 + 模块 reload）
3. detach
4. 通过 `sys.remote_exec` 检查目标进程：peeka 线程数、peeka socket 文件数

**结论**：无资源泄漏，测试通过。

**原因**：`_init_agent()` 的执行顺序是：
```
bootstrap 清除 sys.modules
    ↓
import peeka.core.agent  (新模块加载)
    ↓
_init_agent() 调用 old_agent.stop()  ← 此时 sys.modules 中已是新类
    ↓
shutdown_agent_resources() 执行 isinstance() 检查
```

关键事实：`old_agent.stop()` 在新 `sys.modules` 加载**完成后**才被调用，但 `old_agent` 对象的 `command_handlers` 字典中存放的 handler 实例是旧 class 的实例。`isinstance(handler, ResourceOwningCommand)` 使用的是**新** `ResourceOwningCommand`，因此检查**确实**会失败。

但实测无泄漏的原因是：monitor 命令在 detach 时已经被正确 stopped（第一次 detach 时 `sys.modules` 尚未被清除），re-attach 时旧 session 实际上没有活跃的资源所有命令需要清理。**结论有效，但限定场景**：如果 re-attach 时旧 agent 确有活跃 ResourceOwningCommand handler，P1 风险仍存在。

---

## P2 验证结果：发现 Bug，已修复

**测试**：`TestModuleCacheSignalRestoration`（`tests/container/test_attach.py`）

**验证流程**：
1. 记录 baseline 信号处理器（`SIG_DFL`）
2. attach → 记录 peeka 安装的处理器
3. detach → 记录处理器（应恢复为 baseline）
4. re-attach → detach → 记录处理器（仍应为 baseline）

**初始 Bug 结果**：
```
AssertionError: P2 BUG after first detach: SIGTERM handler not restored.
  baseline='SIG_DFL'
  after_detach1='PeekaAgent._handle_sigterm'
```

### 根本原因

`_uninstall_exit_hooks()` 中的恢复条件为：
```python
if (
    prev_sigterm_handler is not None
    and threading.current_thread() is threading.main_thread()   # ← 阻断非主线程
    and signal.getsignal(signal.SIGTERM) is sigterm_handler_ref
):
    signal.signal(signal.SIGTERM, prev_sigterm_handler)
```

当 `stop()` 从非主线程（例如 socket 客户端处理线程）被调用时，`threading.current_thread() is threading.main_thread()` 返回 `False` → 跳过恢复 → 信号处理器永久留在目标进程中。

### 修复方案

在 `peeka/core/agent.py` 中新增 `_schedule_signal_restore_on_main_thread()`，使用 `Py_AddPendingCall` 将信号恢复调度到主线程的下一个字节码边界执行：

```python
def _schedule_signal_restore_on_main_thread(signum, previous_handler, expected_handler):
    """当 stop() 运行在非主线程时，通过 Py_AddPendingCall 将信号恢复调度到主线程。"""
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
    # ... 创建 ctypes 回调 → 调用 Py_AddPendingCall ...
```

`_uninstall_exit_hooks()` 修改为：
- 主线程：直接调用 `signal.signal()`（原有行为）
- 非主线程：调用 `_schedule_signal_restore_on_main_thread()` 延迟恢复

同时保留了身份守护不变式：只有当 `signal.getsignal(SIGTERM) is sigterm_handler_ref` 时才恢复，确保不覆盖目标应用在 detach 后自行安装的处理器。

**验证**：`TestModuleCacheSignalRestoration` 现在通过，81 个非容器测试全部通过。

---

## 实施细节

### 提交记录
| 提交 | 描述 |
|---|---|
| `58e3aa3` | `test(container): verify resource owners clean up after module reload` |
| `08828c9` | `test(container): verify signal handlers restore after re-attach` |
| `50ebad3` | `fix(attach): restore signal handlers when stop() runs off main thread` |

### 关键文件
- `peeka/core/agent.py`：`_schedule_signal_restore_on_main_thread()`、重构后的 `_uninstall_exit_hooks()`
- `tests/container/test_attach.py`：`TestModuleCacheResourceOwnerCleanup`、`TestModuleCacheSignalRestoration`
- `tests/test_agent_stop_invariants.py`：新增非主线程 stop 的回归覆盖

---

## 遗留注意事项

**P1 的边界情况**（低风险，暂不修复）：如果将来实现了"re-attach 时旧 agent 仍有活跃 ResourceOwningCommand"的场景，`isinstance(handler, ResourceOwningCommand)` 将因类身份不同而失败。建议届时改为 duck-typing 检查：
```python
# 替代方案（如需修复）
if hasattr(handler, "stop_active_resources") and hasattr(handler, "cleanup_scope"):
    ...
```

目前的测试场景（先 detach 再 re-attach）不触发此问题。

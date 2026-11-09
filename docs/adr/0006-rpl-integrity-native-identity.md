# ADR 0006: `rpl_integrity.ok` 的语义：检查原生身份

- 状态：Accepted
- 日期：2026-11-08
- 决策者：peeka 维护者
- 实现：`a7ca456`、`a0ef19d`（`peeka/core/runtime/primitives.py`）
- 相关文档：[runtime-primitive-layer.md](../runtime-primitive-layer.md)

## 上下文

RPL（Runtime Primitive Layer）为 peeka 自己的线程、锁、socket、计时提供原生原语，要在“gevent / eventlet 先 monkey-patch，peeka 后 attach”的进程里正常工作。`patch-status` 的 `rpl_integrity` 字段要回答：peeka 手里的原语是不是安全的。

历史上出现过三种语义：

1. **drift 检测器**（最初实现）：捕获值与**当前**模块属性做 `is` 比较。在 gevent 进程中必然 `ok=false`（`degraded`），而这正是 RPL 要支持的场景，结果会误导用户（codex review 指出）。
2. **“捕获到可调用对象”**（`1035f4f`）：只检查 `callable(captured)`。由于捕获时总有 fallback，`ok` 几乎恒为 true，没有信息量；eventlet 先 patch 时捕获到的是绿色实现，却仍报 `ok=true`（假阳性）。
3. **原生身份**（本决策）。

## 决策

`*_native` 表示“peeka RPL 交出的对象就是 C runtime 实现”，**检查捕获对象本身**，不与 live 模块属性比较：

- 函数类（`start_new_thread`、`get_ident`、`time`、`perf_counter`）：`isinstance(x, types.BuiltinFunctionType)`。gevent / eventlet 的替代品都是纯 Python 函数。
- 锁类：新建对象的类型属于 `_thread`，且名字为 `lock` / `RLock`。按名字比较，因为 eventlet 下看到的 `_thread` 模块本身可能已被替换。
- Event：其内部锁是 `_thread.lock`。
- socket：`_NATIVE_SOCKET.__module__ == "_socket"`。

`ok=false` 因此是**可操作的信号**：peeka 自己的线程或锁被绿化了（例如 eventlet 在 attach 前已 patch），agent 基础设施可能卡住。gevent 正常场景下仍为 `ok=true`。

模块属性与原生实现之间的 drift **由 `patch-status` 的 `stdlib_origin`（`matches` 字段）报告**，不放在 `rpl_integrity` 中。

子决策：

- **gevent**：通过 `gevent.monkey.get_original` 取回原生实现。实测发现 gevent 下 rlock / event 原本拿到的不是原生实现，已在 `a7ca456` 一并修复。
- **eventlet**：只**检测**（被绿化时 `ok=false`），不取回原生实现。取回需要有真实 eventlet 环境的测试，另作后续任务。
- **`captured_at_import`**：直接删除（不保留兼容）。新增 `capture_source`，记录每个原语从哪里捕获（`gevent.get_original` / `module_attr` / `_socket`）。

## 后果

- 非 CPython 下“是否 builtin”的判断可能不成立，需要注意。
- schema 中删除了 `captured_at_import` 字段，读取它的消费者需要调整（目前只有 patch-status 透传，TUI 不读取）。

# ADR 0007: 叠加 probe 的停止顺序与 wrapper 摘除规则

- 状态：Accepted
- 日期：2026-11-08
- 决策者：peeka 维护者
- 实现：`2057291 fix(core): prevent deadlock from stopped probe wrappers on stacked targets`
- 回归测试：`tests/test_probe_stop_order_matrix.py`
- 相关文档：[probe-lifecycle-model.md](../probe-lifecycle-model.md)、[wrapper-ownership.md](../wrapper-ownership.md)

## 上下文

同一函数上可以叠加多个 probe（watch / trace / stack / monitor），再按任意顺序停止，或者通过 reset / detach 一次性清理。审计时用矩阵（多种组合 × 全部停止顺序 × plain / `functools.wraps` × 逐个 stop / reset / detach）复现，发现 `WMTM`（watch + monitor + trace + monitor）等组合在某些停止顺序下，**业务线程会永久挂死**。

## 根因

是死锁，不是死循环：

1. `trace` wrapper 在 probe 已停止或已达到 `-n` 上限时，**持有 `injector._lock` 去调用下一层 func**。如果下一层是 watch / stack / trace wrapper，它会去获取同一把不可重入的锁。最简触发与 monitor 无关：`watch f` + `trace f -n 1`，第 2 次调用 `f` 就会挂死。
2. 已停止的 wrapper 仍留在调用链上：injector 停 probe 时只改上层 wrapper 的 `__wrapped__`，没有改真正被调用的闭包 `func`，也没有通知 monitor。

## 决策

1. **wrapper 不得持锁调用下一层**：在锁内只做判断，出锁后再调用 func。
2. **统一的摘除规则**：原本调用被移除 wrapper 的，改为调用它原本调用的那一层。同时修改闭包和 `__wrapped__`，并同步 `original` / `previous_wrapper` / `root_original`。共用实现为 `registry.py` 中的 `wrapper_call_target` / `retarget_wrapper_call`，取代原来的 `_relink_wrapped_chain`。
3. **跨 registry 通知**：injector 提供 `add_wrapper_removed_listener`。monitor 用 WeakMethod 注册监听，回调在 injector 锁外执行；injector 停 probe 时，monitor 调用链中对应的 wrapper 也会被摘掉。
4. 修正 `monitor._stop_monitor`：`owned_root_original` 原来只在 `elif` 分支更新，可能最终还原到已停止 monitor 的 wrapper。

alias 相关的两个疑点经矩阵验证**不是缺陷**：

- 单次 uninject 时 `_restore_watch_aliases` 使用 `force=False`，是有意为之：不覆盖用户自己重新绑定的 alias。
- 跨 group alias 恢复使用 `root_original`：detach / reset 都先停 monitor，再执行 `uninject_all`，因此最终总能回到原函数。

## 不变式（由矩阵测试保证）

- 调用都带 5 秒超时，用于发现死锁。
- 活跃 probe 有观测，已停止 probe 无观测。
- canonical 与 alias 始终是同一个对象。
- 执行路径上不存在已停止的 wrapper。
- 全部停止后恢复为原函数，注册表为空。

修复前矩阵有 29 个用例失败，修复后 109 个全部通过（约 1 秒）。

# Attach 与 Agent 生命周期问题

| 字段 | 值 |
|------|-----|
| **话题** | 进程 attach 就绪探测、会话文件清理、accept 循环时序与 agent 线程生命周期问题 |
| **受影响组件** | core/attach, core/agent, tui process attach flow |
| **最高严重级别** | SEV-0 (Critical) |
| **事故次数** | 9 |
| **时间跨度** | 2026-02-26 至 2026-06-23 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#9](#事故-9agent-stop-清理合同不完整与信号钩子恢复漂移) | Agent stop 清理合同不完整与信号钩子恢复漂移 | SEV-1 | 2026-06-23 |
| [#8](#事故-8gdb-fallback-injector-build-路径误假设用户安装-uv) | GDB fallback injector build 路径误假设用户安装 uv | SEV-2 | 2026-06-07 |
| [#7](#事故-7attach-异常路径未同步-_last_attach_error) | attach 异常路径未同步 `_last_attach_error` | SEV-2 | 2026-05-25 |
| [#6](#事故-6attach-错误传播改进与-gdb-附加状态解析) | attach 错误传播改进与 GDB 附加状态解析 | SEV-2 | 2026-05-03 |
| [#5](#事故-5首次-attach-间歇性超时) | 首次 attach 间歇性超时 | SEV-2 | 2026-03-01 |
| [#4](#事故-4快速-attachdetach-后-connection-refused) | 快速 attach/detach 后 Connection refused | SEV-1 | 2026-03-01 |
| [#3](#事故-3多次-attachdetach-线程泄漏导致资源耗尽) | 多次 attach/detach 线程泄漏导致资源耗尽 | SEV-0 | 2026-03-01 |
| [#2](#事故-2accept_ready-事件设置过早与线程不可观测) | accept_ready 事件设置过早与线程不可观测 | SEV-1 | 2026-02-27 |
| [#1](#事故-1ready-存在但-socket-尚不可连就绪误判) | `.ready` 存在但 socket 尚不可连(就绪误判) | SEV-2 | 2026-02-26 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题集中暴露 attach 与 agent 的“就绪判定—运行—清理”全链路时序问题：仅依赖 `.ready` 文件会误判就绪；accept 线程 event 设置过早导致连接窗口竞态；首次冷启动导入耗时与固定超时冲突；rapid attach 场景出现脚本清理时序与 stale 文件误判；最终在多次 attach/detach 循环中演化为线程泄漏（SEV-0）。

2026-05-25 的新增事故说明，attach 链路的“错误可观测性”也是同一生命周期合同的一部分。`_attach_internal()` 在捕获异常后会返回 `False` 并发送 progress 事件，但若没有同步 `_last_attach_error`，CLI/TUI 上层只能看到泛化失败状态，无法稳定展示真实错误原因。

2026-06-07 的新增事故说明，attach 的 fallback 路径不能依赖开发者本机工具链。`uv run python setup.py build_ext --inplace` 对仓库开发者方便，但用户容器或生产环境只保证有目标 Python 和编译依赖，不保证安装 uv。attach workflow 必须用当前解释器作为最小假设。

2026-06-23 的新增事故把生命周期问题从 attach 建连阶段推进到 agent 退出阶段：`stop()` 不仅要关闭 socket 和清理会话文件，还必须停止资源所有命令、停止 ProbeContext、恢复 injector、清空 observer，并且只恢复 Peeka 自己仍然持有的 `SIGTERM` / `sys.excepthook` 钩子。退出清理合同不完整会让 detach/reset 看似成功，但目标进程中仍残留 wrapper、采样线程或被覆盖的宿主信号处理器。

---

## 事故 #9：Agent stop 清理合同不完整与信号钩子恢复漂移

> **Tag 范围**：`v0.1.17` → `v0.1.18` | **严重级别**：SEV-1 | **日期**：2026-06-23

### 概要

`PeekaAgent.stop()` 曾主要负责停止 server、清理 session 文件和注销 agent 注册表，但没有把 resource-owning command、ProbeContext、injector wrapper、observer 状态和宿主钩子恢复统一纳入同一个可验证合同。结果是 detach、reset 或信号退出后，目标进程可能残留 monitor/top 采样资源、watch/trace/stack wrapper、ProbeContext 状态，或错误恢复非 Peeka 当前持有的 `SIGTERM` / `sys.excepthook` 钩子。

### 根因分析

#### 类别
Resource Management / Integration Error

#### 分析

根因是 agent 生命周期的“退出”被分散实现：`stop()` 早期只覆盖 socket/session 文件层，resource owner 清理、probe context 停止、injector reset、observer 清空和 probe registry sweep 分散在 detach/reset 层或测试夹具中。`5551a91` 将 `shutdown_agent_resources(self, logger, ["watch", "trace", "stack", "monitor", "top"])` 接入 `PeekaAgent.stop()`，使 stop 成为统一清理入口。

后续修复说明该入口仍有两个合同缺口：

1. `stop_resource_owners_for_detach/reset()` 只记录 handler 抛出的异常，没有汇总 handler 返回值中的 `errors`，导致清理失败被吞掉。
2. `stop_probe_contexts_by_type()` 使用通用 streaming 类型时会错误包含 monitor；而 monitor 是 resource-owning command 管理的资源，reset/stop-all 不应把它当成 injector-managed streaming probe 一并关闭。
3. `signal.getsignal(signal.SIGTERM) is self._handle_sigterm` 使用 bound method 做身份比较不稳定；每次访问 bound method 都可能生成不同对象，导致 Peeka 无法可靠判断当前钩子是否仍由自己持有。

关键修复片段：

```python
shutdown_agent_resources(
    self, logger, ["watch", "trace", "stack", "monitor", "top"]
)

INJECTOR_MANAGED_STREAMING_PROBE_TYPES = frozenset({"watch", "trace", "stack"})

self._sigterm_handler_ref = self._handle_sigterm
self._prev_sigterm_handler = signal.signal(signal.SIGTERM, self._sigterm_handler_ref)
...
if signal.getsignal(signal.SIGTERM) is self._sigterm_handler_ref:
    signal.signal(signal.SIGTERM, self._prev_sigterm_handler)
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交无法确定性定位 | - | 2026-06-21 前 | agent stop、detach、reset 和 resource owner 清理分别演化，缺少统一关闭不变量 |

### 复现

#### 前置条件
- 目标进程中存在 active watch/trace/stack 与 monitor/top 资源。
- agent 注册过 `SIGTERM` 或 `sys.excepthook` 钩子。
- 某个 resource-owning handler 在返回 dict 的 `errors` 字段中报告清理失败。

#### 步骤
1. 启动 monitor/top 后执行 detach 或触发 `agent.stop()`。
2. 让 resource owner 返回 `{"errors": [...]}` 但不抛异常。
3. 在宿主进程中修改 `SIGTERM` 或 `sys.excepthook` 后再调用 `stop()`。

#### 预期行为
所有 Peeka 资源被统一清理；返回式 cleanup error 被上层可见；只在当前钩子仍由 Peeka 持有时恢复旧钩子；宿主自定义钩子不被覆盖。

#### 实际行为
清理步骤分散且部分失败不可见；monitor ProbeContext 可能被错误归入 injector-managed stop-all；bound method 身份比较导致信号钩子恢复判断不可靠。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`5551a91`](https://github.com/peeka-project/peeka/commit/5551a91befd2071b75e108ba23fbad9d441101ee) | lufeihaidao | 2026-06-21 | fix(agent): complete stop() resource cleanup invariants |
| [`aa03ee2`](https://github.com/peeka-project/peeka/commit/aa03ee23f8a7d014074a623254f88961daabab74) | lufeihaidao | 2026-06-21 | fix(agent): honor target SIGTERM disposition (SIG_DFL/callable/SIG_IGN) |
| [`7b0b8fb`](https://github.com/peeka-project/peeka/commit/7b0b8fb334f74a1962d7fd495a3dfe4f3b5267d0) | lufeihaidao | 2026-06-23 | fix(lifecycle): propagate resource-owner returned errors, add injector_managed_streaming_types, guard hook restoration |
| [`bdaf7b9`](https://github.com/peeka-project/peeka/commit/bdaf7b9665fdaf8417ee0b5b21ac97c5f11ca2a1) | lufeihaidao | 2026-06-23 | fix(agent): store stable SIGTERM handler reference for guard comparison |

#### 变更内容
- `PeekaAgent.stop()` 增加幂等 `_stopped/_stop_lock` 保护，并调用 `shutdown_agent_resources()` 执行 resource owner、ProbeContext、injector、observer 和 registry sweep。
- `stop_resource_owners_for_detach/reset()` 汇总返回式 `errors`，不再只捕获异常。
- 新增 `ProbeContext.injector_managed_streaming_types()`，把 watch/trace/stack 与 monitor 生命周期边界拆开。
- `SIGTERM` 处理遵守宿主原有 `SIG_DFL`、callable 和 `SIG_IGN` 语义；钩子恢复使用稳定 `_sigterm_handler_ref` 与 `_peeka_excepthook_ref` 做 guard。

#### 验证
相关修复提交补充了 `tests/test_agent_stop_invariants.py`、`tests/test_agent_excepthook.py`、`tests/test_lifecycle_helper.py`、`tests/test_probe_registry_sweep.py` 等生命周期回归测试；`7b0b8fb` 的提交说明覆盖 returned errors、injector-managed probe types 和 hook restoration 三组测试。

### 影响

- **受影响用户**：频繁 attach/detach、使用 reset、monitor/top、TUI 退出清理或依赖宿主信号处理器的用户。
- **持续时间**：无法从 git 历史确定；缺口在 resource-owning command 和 ProbeContext 引入后逐步累积，至 v0.1.18 修复。
- **数据影响**：无持久数据损坏；风险是目标进程残留诊断 wrapper/采样线程或宿主信号钩子被错误恢复。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-21 前 | agent stop 未统一覆盖所有 Peeka 资源和宿主钩子恢复合同 |
| 2026-06-21 | `5551a91` 将 `shutdown_agent_resources()` 接入 `stop()` |
| 2026-06-21 | `aa03ee2` 修复 SIGTERM 原始 disposition 传播 |
| 2026-06-23 | `7b0b8fb` 暴露 returned errors、probe type 边界和 hook guard |
| 2026-06-23 | `bdaf7b9` 使用稳定 handler reference 修复 bound method 身份比较 |

### 经验教训

#### 做得好的方面
- 生命周期清理被抽象为 `shutdown_agent_resources()`，后续命令可通过 `ResourceOwningCommand.cleanup_scope` 自动接入。
- 修复同时覆盖正常 detach、reset、signal 和 excepthook 退出路径。

#### 可以改进的方面
- 初始 resource owner 合同只规定了调用入口，没有规定“返回式错误必须向上冒泡”。
- 信号钩子恢复使用 Python bound method 身份比较，说明 hook ownership 需要稳定 token，而非临时对象。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为所有 lifecycle cleanup helper 保留“异常 + 返回式 errors”双路径测试 | P0 | 已完成 |
| 将 watch/trace/stack 与 monitor/top 的 lifecycle ownership 写入架构文档 | P1 | 待处理 |
| 对所有宿主全局钩子恢复逻辑统一使用稳定引用或 token guard | P1 | 待处理 |

### 预防

- **立即执行**：agent 退出必须通过统一 shutdown helper，禁止新增绕过 helper 的清理路径。
- **短期**：清理结果 schema 固定为 step errors + resource owner errors + probe context errors，并在 CLI/TUI 层可见。
- **长期**：建立生命周期状态机测试矩阵，覆盖 detach/reset/stop/signal/excepthook/重复调用。

### 参考

- 修复提交：`5551a91`, `aa03ee2`, `7b0b8fb`, `bdaf7b9`

---

## 事故 #8：GDB fallback injector build 路径误假设用户安装 uv

> **Tag 范围**：`v0.1.15` → `v0.1.16` | **严重级别**：SEV-2 | **日期**：2026-06-07

### 概要

pre-3.14 的 GDB fallback 路径需要 C injector extension。实现中曾直接运行 `uv run python setup.py build_ext --inplace` 来构建 injector。这对开发仓库有效，但用户实际环境未必安装 uv；在容器或普通 pip 安装场景中，attach 会因为找不到 uv 而失败，即使系统具备 Python、GDB 和 ptrace 能力。

### 根因分析

#### 类别
Environment Assumption / Attach Workflow Regression

#### 分析

attach workflow 把“项目开发环境命令”当成了“目标用户环境命令”：

```text
uv run python setup.py build_ext --inplace
```

该命令隐含两个错误假设：

1. 用户环境安装了 uv。
2. peeka 源码以可编辑仓库形式存在，而不是普通 wheel/site-packages 安装。

对于 Python 3.8-3.13，GDB fallback 本身已经要求 GDB、python debug symbols 和 ptrace；但这些是 attach 机制的必要条件，uv 不是。构建 extension 应使用当前解释器或已安装 artifact，不应把开发工具暴露为运行时要求。

### 复现

#### 前置条件
- Python 3.8-3.13 目标进程。
- 环境可执行 `python`，但没有安装 `uv`。
- 需要走 GDB fallback injector 路径。

#### 步骤
1. 在没有 uv 的容器中运行 peeka attach。
2. 触发 `_build_injector_if_needed()`。

#### 预期行为
使用当前 Python 解释器构建或发现 injector，attach 继续进行；缺少编译依赖时给出针对 GDB/injector 的错误。

#### 实际行为
构建命令因 `uv` 不存在而失败，attach 直接中断。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`8f510a9`](https://github.com/peeka-project/peeka/commit/8f510a963b0da9d934c2a84242822577f693fad6) | lufeihaidao | 2026-06-07 | fix(attach): remove uv assumption from injector build path |

#### 变更内容

- attach 构建 injector 时不再调用 `uv run`。
- 使用当前 Python 解释器作为 build command 的基础。
- 文档补充 pre-3.14 场景下“挂载源码仍需 build extension”的说明，避免用户误以为源码 volume mount 即可直接运行所有 attach 路径。

#### 验证
- `tests/test_attach_refactor.py` 覆盖错误消息中不再出现 `uv run`。
- `v0.1.16` 发布流水线 `publish-pypi.yml` 通过。

### 影响

- **受影响用户**：未安装 uv 的 Python 3.8-3.13 用户、容器环境、只按运行时依赖安装 peeka 的用户。
- **持续时间**：同一 release 开发周期内发现并修复，未进入成功发布的 PyPI 版本。
- **数据影响**：无。影响是 attach fallback 不可用。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-07 | review 发现 attach build command 依赖 uv |
| 2026-06-07 | `8f510a9` 移除 uv 假设 |
| 2026-06-07 | 文档补充 pre-3.14 injector build 要求 |
| 2026-06-07 | `v0.1.16` 发布流水线验证通过 |

### 经验教训

#### 做得好的方面
- 问题在 release 前通过环境假设 review 发现。
- 修复将运行时要求收敛到当前解释器，减少用户环境依赖。

#### 可以改进的方面
- attach fallback 的环境要求应以“用户安装场景”为基准，而不是以开发仓库为基准。
- 所有 subprocess build command 都应有“无 uv/无 dev tool”测试。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 attach injector build command 保留“不依赖 uv”的单元测试 | P0 | 已完成 |
| 在容器测试矩阵中覆盖无 uv 的 pre-3.14 attach 环境 | P1 | 待处理 |

### 预防

- **立即执行**：运行时路径禁止调用 `uv run`、`poetry run` 等开发环境命令。
- **短期**：审计 attach、docker、container helper 中的 build/install 命令，区分开发命令与用户命令。
- **长期**：在 release gate 中加入“minimal user environment” smoke test。

### 参考

- 修复提交：`8f510a9`

---

## 事故 #7：attach 异常路径未同步 `_last_attach_error`

> **Tag 范围**：`v0.1.14` → `v0.1.15` | **严重级别**：SEV-2 | **日期**：2026-05-25

### 概要

`ProcessAttacher._attach_internal()` 的总异常捕获路径会记录日志并发出失败 progress，但没有把异常文本写入 `_last_attach_error`。当上层依赖该字段构造最终错误消息时，用户会看到缺失或陈旧的失败原因，降低 attach 问题的可诊断性。

### 根因分析

#### 类别
Observability Gap / Integration Error

#### 分析

异常处理块只做了 progress 事件和日志输出：

```python
except Exception as e:
    self._emit_progress(...)
    logger.error("Attach failed: %s", e)
    return False
```

这使 `_attach_internal()` 的返回值和进度流能表达失败，但对象状态中的 `_last_attach_error` 没有被更新。后续调用者若读取该字段，就无法获得导致失败的原始异常信息。该缺口与话题 #6 的“attach 错误传播”同属一类：错误已经发生，但没有被完整传递到最终用户可见层。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | - | 2026-05-25 前 | `_last_attach_error` 字段被引入后，`_attach_internal()` 的通用异常捕获路径未同步维护该字段 |

### 复现

#### 前置条件
- 构造一个会在 `_check_existing_attachment()` 或 attach 准备阶段抛异常的 attach 流程。

#### 步骤
1. 创建 `ProcessAttacher(12345)`。
2. 让 `_check_existing_attachment()` 抛出 `RuntimeError("Mocked attach failure")`。
3. 调用 `_attach_internal()`。
4. 检查返回值和 `_last_attach_error`。

#### 预期行为
`_attach_internal()` 返回 `False`，且 `_last_attach_error == "Mocked attach failure"`。

#### 实际行为
`_attach_internal()` 返回 `False`，但 `_last_attach_error` 未记录本次异常。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`09a825e`](https://github.com/peeka-project/peeka/commit/09a825e56b4e1418e87e77301d2082d94027c976) | lufeihaidao | 2026-05-25 | fix(core): save exception to _last_attach_error in _attach_internal |

#### 变更内容

在 `_attach_internal()` 的通用异常处理块中写入异常文本：

```python
except Exception as e:
    self._last_attach_error = str(e)
    self._emit_progress(...)
    return False
```

同时新增回归测试 `test_attach_internal_saves_last_error_on_exception`，直接覆盖异常路径。

#### 验证
- `tests/test_attach_refactor.py` 新增异常路径断言。
- `v0.1.15` 发布流水线 `publish-pypi.yml` 的测试 job 通过。

### 影响

- **受影响用户**：attach 失败并依赖 CLI/TUI 最终错误信息定位问题的用户。
- **持续时间**：无法从 git 历史确定；缺口存在于 `_last_attach_error` 字段被上层消费之后。
- **数据影响**：无。影响仅限错误诊断质量。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-25 前 | `_attach_internal()` 异常路径未维护 `_last_attach_error` |
| 2026-05-25 | 修复提交 `09a825e` 合入 |
| 2026-05-27 | `v0.1.15` 发布流水线验证通过 |

### 经验教训

#### 做得好的方面
- 修复范围很小，直接在唯一异常出口补齐状态更新。
- 回归测试使用故障注入覆盖精确路径，避免只验证日志或返回值。

#### 可以改进的方面
- attach 错误传播字段应有统一不变量：任何返回 `False` 的失败路径都必须设置可读错误原因。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 attach 失败路径补充“返回 False 必须携带错误原因”的参数化测试 | P1 | 待处理 |

### 预防

- **立即执行**：保持新增回归测试，防止通用异常路径再次丢失错误状态。
- **短期**：审计 `_attach_pep768()`、`_attach_fallback()` 和 `_wait_for_agent_ready()` 的所有 `False` 返回路径。
- **长期**：将 attach 失败结果建模为结构化错误对象，减少“返回值 + side-channel 字段”的同步风险。

### 参考

- 修复提交：`09a825e`

---

## 事故 #6：attach 错误传播改进与 GDB 附加状态解析

> **Tag 范围**：`v0.1.8..v0.1.9` | **严重级别**：SEV-2 | **日期**：2026-05-03
> **相关提交**：`88da13e fix(core): improve attach reliability and error surfacing`

### 概要

attach 失败时错误信息不足，用户难以定位是 GDB 问题、Python 版本问题还是进程权限问题。

### 根因分析

#### 类别
Observability Gap

#### 分析
原始实现中 GDB attach 失败直接抛出通用异常，缺少：
1. GDB 子进程 exit code 捕获
2. GDB stdout/stderr 输出透传
3. Python 3.14 PEP 768 与 GDB fallback 路径的状态区分

### 复现步骤
1. 对无 ptrace 权限的进程执行 attach
2. 观察错误：仅"attach failed"，无具体原因

### 修复详情

```python
# Linux fallback 根据目标 Python 版本选择注入路径：
# Python 3.8 及以下优先 legacy GDB，避免 dlopen 路径的线程调度问题。
target_version = self._get_target_python_version()
prefer_legacy_gdb = (
    system_name == "Linux"
    and target_version is not None
    and target_version <= (3, 8)
)

if not prefer_legacy_gdb:
    try:
        return self._inject_via_gdb()
    except (TimeoutError, RuntimeError, OSError) as e:
        logger.warning("GDB dlopen injection failed (%s), falling back to legacy GDB", e)

# GDB/LLDB 子进程失败时在异常信息中携带 return code、stderr、stdout。
if result.returncode != 0:
    raise RuntimeError(
        f"GDB injection failed (exit code {result.returncode}):\n"
        f"stderr: {result.stderr}\n"
        f"stdout: {result.stdout}"
    )
```

### 经验教训

1. **错误传播是调试体验的核心** — 用户遇到 attach 失败时首先需要知道"是我的环境问题吗"
2. **跨层错误需要结构化** — CLI 层需要结构化异常来格式化友好输出，而不是字符串拼接
3. **fallback 路径需要状态可见** — 用户需要知道当前使用的是 PEP 768 还是 GDB

### 预防措施

- [x] Python 3.8 及以下优先使用 legacy GDB fallback
- [x] GDB/LLDB 失败信息包含 exit code、stderr、stdout
- [x] CLI attach 使用 `suppress_startup_messages=True` 保持 JSONL 输出纯净
- [x] TUI attach 失败时显示包含 traceback 的错误弹窗

---

## 事故 #5：首次 attach 间歇性超时

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-03-01

### 概要

首次向冷进程注入时偶发超时，用户需手动重试。核心原因是模块冷加载时间超过硬编码 5 秒。

### 根因分析

#### 类别
Configuration Error

#### 分析
首次注入需导入 13+ 命令模块，慢盘或高负载下超过 5 秒；且原流程无自动重试。

```python
max_attempts = 2
for attempt in range(max_attempts):
    try:
        if self._wait_for_agent_ready():
            return True
    except TimeoutError:
        if attempt < max_attempts - 1:
            # retry
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | 初始 attach 使用固定 5 秒超时且无重试 |

### 复现

#### 前置条件
- 慢速机器或高负载环境

#### 步骤
1. 对从未注入过的进程执行首次 attach。

#### 预期行为
首次 attach 稳定成功。

#### 实际行为
约 30% 概率 5 秒超时失败。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `7d505e9` | 未记录 | 2026-03-01 | fix(attach): increase timeout and add retry for intermittent first-attach failure |

#### 变更内容
1. 超时 5s → 10s。
2. 新增一次自动重试（总 2 次）。

#### 验证
首次 attach 成功率显著提升，超时场景可自动恢复。

### 影响

- **受影响用户**：首次 attach 冷启动用户
- **持续时间**：初始实现至 `7d505e9`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | 固定 5 秒超时且无重试 |
| 2026-03-01 | `7d505e9` 增加超时与重试 |

### 经验教训

#### 做得好的方面
- 通过“更长超时 + 重试”兼顾稳定性与用户体验。

#### 可以改进的方面
- 冷启动时延未纳入初始容量预算。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 记录首次注入耗时分布并动态调参 | P1 | 待处理 |

### 预防

- **立即执行**：冷启动路径使用宽松超时。
- **短期**：超时失败默认重试一次。
- **长期**：引入自适应超时机制。

### 参考

- 修复提交：`7d505e9`

---

## 事故 #4：快速 attach/detach 后 Connection refused

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-03-01

### 概要

在 rapid attach 场景中第二次 attach 间歇失败。原因是注入脚本被过早删除与会话文件残留共同造成时序误判。

### 根因分析

#### 类别
Race Condition

#### 分析
1. `sys.remote_exec()` 为 fire-and-forget，`process_selector.py` 在 finally 调 `attacher.cleanup()` 可能提前删除目标尚未读取的脚本。
2. `agent.stop()` 未清理 `/tmp/peeka_{session_id}.{sock,ready,pid}`，`_check_existing_attachment()` 被 stale 文件误导为“已附加”。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | 初始 TUI attach 流程含脚本清理时序与会话文件残留问题 |

### 复现

#### 前置条件
- 同一进程快速重复 attach/detach

#### 步骤
1. 在 TUI 执行 attach → detach → attach。

#### 预期行为
第二次 attach 正常。

#### 实际行为
第二次 attach 失败（Connection refused）。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `7a3066e` | 未记录 | 2026-03-01 | fix(tui): fix connection refused on rapid attach by cleaning up session files on detach |

#### 变更内容
1. `process_selector` finally 中不再立刻 `attacher.cleanup()`（避免脚本过早删除）。
2. `agent.stop()` 增加 `_cleanup_session_files()`，删除 `.sock/.ready/.pid`。

#### 验证
rapid attach/detach 可稳定成功，不再被 stale 文件误判。

### 影响

- **受影响用户**：频繁切换 attach 会话用户
- **持续时间**：初始流程至 `7a3066e`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | 过早清理脚本 + 会话文件残留 |
| 2026-03-01 | `7a3066e` 修复 detach 清理策略 |

### 经验教训

#### 做得好的方面
- 同时修复注入前后两个时序窗口。

#### 可以改进的方面
- fire-and-forget 语义未在流程设计中显式体现。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 对 attach/detach 增加高频循环稳定性测试 | P0 | 待处理 |

### 预防

- **立即执行**：fire-and-forget 之后禁止立即清理依赖文件。
- **短期**：detach 统一清理会话副产物。
- **长期**：会话状态改为主动探测而非文件存在判断。

### 参考

- 修复提交：`7a3066e`

---

## 事故 #3：多次 attach/detach 线程泄漏导致资源耗尽

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-0 | **日期**：2026-03-01

### 概要

重复 attach/detach 后 accept 线程与客户端线程残留，线程数持续增长，最终资源耗尽并可能 OOM 崩溃。

### 根因分析

#### 类别
Resource Management

#### 分析
三项缺陷叠加：
1. `server.accept()` 无超时，无法周期检查 `self.running`。
2. 新注入前未清理旧 agent，旧实例留在 `sys._peeka_agents`。
3. `server.close()` 缺少错误处理。

关键修复代码：

```python
# Set timeout so accept() doesn't block forever
self.server.settimeout(1.0)

# In accept loop:
except socket.timeout:
    # Periodic wakeup to re-check self.running
    continue
except OSError:
    # Server socket closed (stop() called) — exit cleanly
    break

# On init: stop ALL existing agents from previous sessions
if hasattr(sys, "_peeka_agents"):
    old_agents = list(sys._peeka_agents.values())
    for old_agent in old_agents:
        old_agent.stop()
    sys._peeka_agents.clear()
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | 初始 agent 生命周期管理未覆盖退出与重注入清理 |

### 复现

#### 前置条件
- 同一进程反复 attach/detach

#### 步骤
1. 循环 10 次 attach → detach。
2. 观察 `ps -T <pid> | wc -l`。

#### 预期行为
线程数稳定。

#### 实际行为
线程数持续增长。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `567d1c7` | 未记录 | 2026-03-01 | fix(agent): implement timeout for accept loop and cleanup of previous agents to prevent thread leaks |

#### 变更内容
1. `accept` 加 1s timeout。
2. 新会话初始化前停掉并清空全部旧 agent。
3. `stop` 时从注册表反注册。
4. `server.close()` 增加异常处理。

#### 验证
循环 attach/detach 后线程数不再增长。

### 影响

- **受影响用户**：长生命周期目标进程与高频 attach 用户
- **持续时间**：初始实现至 `567d1c7`
- **数据影响**：无直接数据损坏，但有进程稳定性风险

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | accept 永久阻塞 + 旧 agent 未清理 |
| 2026-03-01 | `567d1c7` 修复超时与全局清理 |

### 经验教训

#### 做得好的方面
- 一次修复覆盖线程退出、实例回收、异常关闭三层。

#### 可以改进的方面
- 初始实现未将“重注入”作为一等场景设计。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 引入 attach/detach 长循环压力测试到 CI | P0 | 待处理 |

### 预防

- **立即执行**：阻塞 accept 必设 timeout。
- **短期**：每次注入前执行旧实例审计与清理。
- **长期**：统一 agent 进程内生命周期管理器。

### 参考

- 修复提交：`567d1c7`

---

## 事故 #2：accept_ready 事件设置过早与线程不可观测

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-27

### 概要

attach 间歇失败，且线程默认命名导致调试困难。根因是 `accept_ready` 在 accept 线程真正进入循环前被设置。

### 根因分析

#### 类别
Race Condition

#### 分析
等待方看到 ready 后立即连接，但 accept 线程尚未开始 `accept()`；同时线程名均为 `Thread-*`，问题定位成本高。

```python
# In accept loop thread:
self.server.listen(5)
self.server.settimeout(1.0)
accept_ready.set()  # Set AFTER entering the loop context

while self.running:
    # accept ...
```

并新增线程命名：
- `peeka-agent-accept`
- `peeka-agent-client-{counter}`

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-27 前 | agent 初始 accept 时序与线程命名策略缺失 |

### 复现

#### 前置条件
- 反复 attach/detach

#### 步骤
1. 执行多轮 attach→detach。

#### 预期行为
稳定连接且线程易于识别。

#### 实际行为
约 20% 失败，线程难以定位。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `30fbb62` | 未记录 | 2026-02-27 | fix(agent): name threads and fix accept loop race condition |

#### 变更内容
1. `accept_ready` 改为在 accept 循环上下文中设置。
2. 全部 peeka 线程显式命名。

#### 验证
attach 稳定性提升，`ps/top` 可快速识别线程职责。

### 影响

- **受影响用户**：attach 高频用户与排障人员
- **持续时间**：初始实现至 `30fbb62`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-27 前 | ready 事件过早设置 |
| 2026-02-27 | `30fbb62` 修复时序并命名线程 |

### 经验教训

#### 做得好的方面
- 同时提升稳定性与可调试性。

#### 可以改进的方面
- 线程启动时序缺少设计约束文档。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 线程事件设置时机写入并发开发规范 | P1 | 待处理 |

### 预防

- **立即执行**：ready 事件必须在“可服务”后设置。
- **短期**：线程命名规则强制化。
- **长期**：并发初始化流程可视化与断言化。

### 参考

- 修复提交：`30fbb62`

---

## 事故 #1：`.ready` 存在但 socket 尚不可连（就绪误判）

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-02-26

### 概要

attach 成功返回后立即连接 agent socket 间歇 `Connection refused`。原因是仅以 `.ready` 文件判定就绪。

### 根因分析

#### 类别
Race Condition

#### 分析
`.ready` 文件只证明流程走到 bind 后，不保证 accept 循环已可接收连接。

两阶段修复：
1. 等待 `.ready` 出现。
2. 主动探测 socket 可连接性。

```python
def _wait_for_agent_ready(self, timeout: int = 5) -> bool:
    # Phase 1: Wait for .ready file
    while time.time() - start_time < timeout:
        if ready_file.exists():
            break
    # Phase 2: Verify socket is actually connectable
    while time.time() - start_time < timeout:
        if self._is_socket_alive(socket_path):
            return True
        time.sleep(0.05)
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-26 前 | `_wait_for_agent_ready` 初始实现仅检测 ready 文件 |

### 复现

#### 前置条件
- 慢速机器或高抖动环境

#### 步骤
1. 多次执行 attach。

#### 预期行为
attach 后 socket 立即可连。

#### 实际行为
约 20% 概率连接拒绝。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `73d1fb5` | 未记录 | 2026-02-26 | fix(attach): verify socket connectivity in _wait_for_agent_ready |

#### 变更内容
在 ready 文件检测后增加 socket 主动连通性探测，双条件满足才返回成功。

#### 验证
连接失败概率显著下降，慢速机器稳定性提升。

### 影响

- **受影响用户**：attach 用户
- **持续时间**：初始实现至 `73d1fb5`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-26 前 | 仅以 ready 文件判定就绪 |
| 2026-02-26 | `73d1fb5` 增加 socket 连通性探测 |

### 经验教训

#### 做得好的方面
- 明确将“可连接性”定义为就绪标准。

#### 可以改进的方面
- 被动文件信号被过度信任。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 所有就绪检测统一采用“信号+主动探测”双阶段 | P1 | 待处理 |

### 预防

- **立即执行**：禁止单一文件信号作为最终就绪依据。
- **短期**：在 attach 日志输出两阶段耗时，便于诊断。
- **长期**：统一 readiness 协议与健康检查接口。

### 参考

- 修复提交：`73d1fb5`

# 进程发现与运行时环境适应性问题

| 字段 | 值 |
|------|-----|
| **话题** | Python 进程发现、pycache 目录写入权限、以及非标准运行环境下的降级策略 |
| **受影响组件** | peeka/__init__.py, core/processes |
| **最高严重级别** | SEV-2 (Medium) |
| **事故次数** | 1 |
| **时间跨度** | 2026-06-24 至 2026-06-24 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#1](#事故-1sudo-环境下-pycache-写入失败与-proc-不可用时进程发现中断) | sudo 环境下 pycache 写入失败与 /proc 不可用时进程发现中断 | SEV-2 | 2026-06-24 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题关注 Peeka 在特权或受限运行环境下的自举能力。诊断工具经常需要在 `sudo` 下 attach 到系统服务或其他用户进程，但普通用户的 `__pycache__` 路径在 sudo 环境下可能不可写；同时 `/proc` 在某些容器或加固主机上可能被隐藏或受限，导致基于 `/proc` 的进程发现失效。Peeka 的启动路径和进程发现需要具备环境感知和降级能力，而不是依赖“当前用户可写 pycache”和“/proc 总是可用”这两个假设。

---

## 事故 #1：sudo 环境下 pycache 写入失败与 /proc 不可用时进程发现中断

> **Tag 范围**：`v0.1.18` → `v0.1.19` | **严重级别**：SEV-2 | **日期**：2026-06-24

### 概要

在 `sudo` 下运行 `peeka` 或 `peeka-cli` 时，Python 解释器可能尝试在普通用户目录下写入 `__pycache__`，因权限不足抛出 `PermissionError`，导致 import 阶段即失败。即使成功启动，进程发现模块默认读取 `/proc/<pid>/cmdline` 来枚举 Python 进程；当 `/proc` 不可用或受限时，进程列表为空，用户无法选择目标进程。

### 根因分析

#### 类别
Environment Assumption / Missing Fallback

#### 分析

根因是启动路径和进程发现都隐含了开发者本机环境：

1. **pycache 写入假设**：默认情况下 Python 会把 `.pyc` 文件写入源码目录下的 `__pycache__`。当 Peeka 通过 pip 安装到系统 site-packages 后，普通用户目录在 sudo 下可能变为只读或属主不同，导致首次 import 编译失败。
2. **/proc 唯一依赖**：`discover_python_processes()` 只实现了 `/proc` 遍历，没有为容器、chroot 或加固系统提供替代来源。

这两个问题都属于“运行环境适应性”缺口：诊断工具必须在比开发环境更受限的条件下工作。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交无法确定性定位 | - | 2026-06-24 前 | 进程发现只实现 /proc 路径；启动路径未设置 sudo 安全的 pycache 策略 |

### 复现

#### 前置条件
- 通过 pip 将 Peeka 安装到普通用户可写、但 sudo 后不可写的目录；或容器内 `/proc` 被限制。

#### 步骤
1. 在 sudo 下执行 `peeka` 或 `peeka-cli`。
2. 或在 `/proc` 受限的环境中调用进程发现。

#### 预期行为
- Peeka 能正常启动，不因为 pycache 写入权限失败。
- 进程发现至少能返回可用列表，即使 `/proc` 不可用。

#### 实际行为
- import 阶段抛出 `PermissionError`。
- 或进程发现返回空列表，TUI 进程选择器无目标可选。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`4b25aa6`](https://github.com/peeka-project/peeka/commit/4b25aa690098a10d083478be51e5df3cb09ea70c) | lufeihaidao | 2026-06-24 | fix(import,processes): sudo-safe pycache redirect and ps fallback |

#### 变更内容

- 在 `peeka/__init__.py` 顶部检测运行用户与安装目录属主是否一致；不一致时设置 `PYTHONPYCACHEPREFIX` 到 `/tmp` 下的临时位置，并把 `sys.pycache_prefix` 指向该位置。
- 使用注入式函数 `_geteuid` 便于测试，不直接依赖 `os.geteuid()`。
- 在 `peeka/core/processes.py` 的 `discover_python_processes()` 中增加 `ps` 命令降级路径：当 `/proc` 不存在或遍历结果为空时，调用 `ps -eo pid,comm,args` 并解析输出。
- 增加边界测试覆盖 sudo 用户切换、`/proc` 不可用、以及 `ps` 输出格式差异。

#### 验证

新增测试：
- `tests/test_import_policy.py`
- `tests/test_processes.py` 中扩展的 ps fallback 边界测试

### 影响

- **受影响用户**：在 sudo 下使用 Peeka 的用户；在容器或受限主机上使用进程发现的用户。
- **持续时间**：从相关代码引入至 v0.1.19 修复。
- **数据影响**：无持久数据损坏；风险是无法启动或无法发现目标进程。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-24 前 | 启动路径和进程发现依赖普通用户环境假设 |
| 2026-06-24 | 修复提交 `4b25aa6` 增加 sudo 安全 pycache 重定向和 ps fallback |

### 经验教训

#### 做得好的方面
- 修复通过环境变量和函数注入保持可测试性，没有引入全局不可控的副作用。

#### 可以改进的方面
- 运行环境适应性应在 CI 中通过容器矩阵覆盖，包括 sudo、/proc 受限、不同安装属主等场景。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 在 CI 中增加 sudo 和受限 /proc 的容器测试 | P1 | 待处理 |
| 文档化 Peeka 在特权/受限环境下的使用建议 | P2 | 待处理 |

### 预防

- **立即执行**：所有在启动阶段依赖文件系统写入的代码必须假设安装目录可能只读。
- **短期**：所有外部系统信息来源（/proc、/sys、ps、lsof 等）都应有降级路径。
- **长期**：建立“环境适应性”测试矩阵，覆盖不同权限模型和容器约束。

### 参考

- 修复提交：`4b25aa6`
- 相关测试：`tests/test_import_policy.py`, `tests/test_processes.py`

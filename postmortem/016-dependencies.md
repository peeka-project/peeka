# 依赖配置问题

| 字段 | 值 |
|------|-----|
| **话题** | 依赖声明格式过时或版本约束不兼容导致安装/构建失败 |
| **受影响组件** | dependencies, pyproject.toml |
| **最高严重级别** | SEV-3 (Low) |
| **事故次数** | 2 |
| **时间跨度** | 2026-03-20 至 2026-04-12 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#2](#事故-2dev-dependencies-使用已废弃的-tooluv-字段导致-deprecation-warning) | dev-dependencies 使用已废弃的 `[tool.uv]` 字段导致 deprecation warning | SEV-4 | 2026-04-12 |
| [#1](#事故-1textual-下界过高导致-python-38-无法安装-peeka-tui) | textual 下界过高导致 Python 3.8 无法安装 peeka[tui] | SEV-3 | 2026-03-20 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题涵盖 `pyproject.toml` 依赖声明相关的配置问题：包括版本约束设置不当导致低版本 Python 无法安装，以及依赖声明字段使用已废弃格式导致警告。两次事故均属于 Python 打包生态演进带来的维护成本，需要定期审计依赖配置与工具兼容性。

---

## 事故 #2：dev-dependencies 使用已废弃的 `[tool.uv]` 字段导致 deprecation warning

> **Tag 范围**：`v0.1.7` → `v0.1.8` | **严重级别**：SEV-4 | **日期**：2026-04-12

### 概要

`pyproject.toml` 中使用了 `[tool.uv]` 下的 `dev-dependencies` 字段声明开发依赖，该字段在近期 uv 版本中已废弃，运行 `uv sync` 时产生 deprecation warning。迁移至 PEP 735 标准的 `[dependency-groups]` 表后警告消除。

### 根因分析

#### 类别
Configuration Error

#### 分析

uv 工具在近期版本中将 `[tool.uv] dev-dependencies` 标记为废弃，推荐迁移至 PEP 735 引入的标准 `[dependency-groups]` 表格。原配置：

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=7.0",
    ...
]
```

迁移后：

```toml
[dependency-groups]
dev = [
    "pytest>=7.0",
    ...
]
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交无法确定性定位（初始采用 `[tool.uv]` 格式时 uv 尚未废弃该字段） | — | — | — |

### 复现

#### 前置条件
- 使用较新版本的 uv（已将 `[tool.uv] dev-dependencies` 标记废弃）

#### 步骤
1. 执行 `uv sync --dev`

#### 预期行为
正常同步开发依赖，无警告

#### 实际行为
输出 deprecation warning，提示 `[tool.uv] dev-dependencies` 已废弃

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`11ff017`](https://github.com/wwulfric/peeka/commit/11ff017fa6948546f2ad4290c772b5e183b43441) | wuxing | 2026-04-12 | fix: migrate dev-dependencies to PEP 735 dependency-groups (#12) |

#### 变更内容
将 `[tool.uv] dev-dependencies` 迁移至标准 `[dependency-groups] dev`，消除废弃警告，符合 PEP 735 规范。

#### 验证
迁移后 `uv sync --dev` 无警告输出。

### 影响

- **受影响用户**：所有开发者在 `uv sync` 时看到 deprecation warning
- **持续时间**：从 uv 废弃该字段到 v0.1.8 修复
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 未知 | 初始采用 `[tool.uv] dev-dependencies` 格式 |
| 2026-04-12 | uv 废弃警告被识别 |
| 2026-04-12 | 修复提交：`11ff017` |

### 经验教训

#### 做得好的方面
- 快速响应工具链废弃通知，跟进 PEP 735 标准。

#### 可以改进的方面
- 未在 uv 发布新版本时主动检查废弃变更。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 定期检查 uv/pip/setuptools 版本变更日志，主动迁移废弃配置 | P2 | 待处理 |

### 预防

- **立即执行**：优先使用标准 PEP 规范字段，避免工具私有扩展字段。
- **短期**：在 CI 中开启依赖工具的 warning-as-error 模式，及早发现废弃问题。
- **长期**：订阅 uv/pip 变更日志，定期审计 pyproject.toml 配置。

### 参考

- 修复 PR/提交：`11ff017 fix: migrate dev-dependencies to PEP 735 dependency-groups (#12)`
- 相关 issue：#12

---


## 事故 #1：textual 下界过高导致 Python 3.8 无法安装 peeka[tui]

> **Tag 范围**：`未提供` → `未提供` | **严重级别**：SEV-3 | **日期**：2026-03-20

### 概要

Python 3.8 环境执行 `uv pip install -e ".[tui]"` 失败。原因是 `pyproject.toml` 使用了过高 textual 版本约束，无法找到兼容解。调整约束后，3.8 可完成安装并运行 TUI。

### 根因分析

#### 类别
Dependency Issue

#### 分析
来源文件指出 textual 约束从高下界放宽后问题解决，说明原配置与 Python 3.8 支持矩阵不兼容：
- 原约束：`textual >= 0.40.0`
- 修复约束：`textual >= 0.38.0`

对应变更片段（原文保留）：

```toml
textual = "^0.40.0"
```

改为：

```toml
textual = ">=0.38.0"
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 添加 TUI 依赖时设置过高最低版本 |

> 致因提交无法确定性定位；来源文件仅说明“添加 TUI 依赖时设置了过高的最低版本”。

### 复现

#### 前置条件
- Python 3.8 环境
- 依赖配置中 textual 约束过高

#### 步骤
1. 在 Python 3.8 环境尝试安装 `peeka[tui]`。
2. 执行 `uv pip install -e ".[tui]"`。

#### 预期行为
应解析并安装到兼容 textual 版本。

#### 实际行为
安装失败，无法找到兼容版本。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `53b42f8` | 未提供 | 2026-03-20 | fix(dependencies): adjust textual version constraints for Python compatibility |

#### 变更内容
将 textual 约束从 `^0.40.0` 调整为 `>=0.38.0`，放宽版本空间以支持 Python 3.8 兼容版本解析。

#### 验证
Python 3.8 可以成功安装 textual，TUI 正常运行。

### 影响

- **受影响用户**：Python 3.8 下安装 `peeka[tui]` 的用户。
- **持续时间**：从高下界引入到 `53b42f8` 修复提交。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 添加 TUI 依赖时设置过高下界 |
| 2026-03-20 | Python 3.8 安装失败被发现 |
| 2026-03-20 | 修复提交：`53b42f8` |
| 2026-03-20 | 安装与运行验证通过 |

### 经验教训

#### 做得好的方面
- 快速识别并定位到依赖约束。
- 修复后验证了安装与运行结果。

#### 可以改进的方面
- 多 Python 版本项目的下界策略不够保守。
- 跨版本安装验证不足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 支持的 Python 版本全部执行 `.[tui]` 安装验证 | P1 | 待处理 |
| 调整依赖约束时检查最低 Python 版本兼容性 | P1 | 待处理 |

### 预防

- **立即执行**：避免将最低依赖设得过高。
- **短期**：给依赖求解器保留兼容版本选择空间。
- **长期**：在所有支持 Python 版本上持续执行安装测试。

### 参考

- 修复 PR/提交：`53b42f8 fix(dependencies): adjust textual version constraints for Python compatibility`
- 相关 issue：未提供

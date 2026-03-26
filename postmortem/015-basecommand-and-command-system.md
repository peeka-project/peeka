# BaseCommand 与命令系统参数契约

| 字段 | 值 |
|------|-----|
| **话题** | BaseCommand 缺少 agent 参数导致命令实例化异常 |
| **受影响组件** | commands/base.py, agent command dispatch |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 1 |
| **时间跨度** | 2026-02-05 至 2026-02-05 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#1](#事故-1basecommand-未接收-agent-参数触发-typeerror) | BaseCommand 未接收 agent 参数触发 TypeError | SEV-1 | 2026-02-05 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题体现了命令系统重构中的构造参数契约漂移：Agent 侧开始向命令构造函数传递 `agent`，但基类 `BaseCommand` 未同步接收，导致命令在创建阶段发生 TypeError。修复通过更新基类签名并保存 `self.agent`，恢复命令系统一致性，同时使用 `TYPE_CHECKING` 处理类型导入循环问题。

---

## 事故 #1：BaseCommand 未接收 agent 参数触发 TypeError

> **Tag 范围**：`未提供` → `未提供` | **严重级别**：SEV-1 | **日期**：2026-02-05

### 概要

执行需要 agent 的命令时抛出 `BaseCommand.__init__() takes 1 positional argument but 2 were given`。重构后 Agent 传入 `agent`，而 `BaseCommand` 构造函数未更新，导致命令系统高频路径崩溃。

### 根因分析

#### 类别
Integration Error

#### 分析
命令实例化调用方与基类构造函数签名不一致：
- 调用方传 `agent`
- 基类仅定义 `def __init__(self)`

该不一致直接在实例化阶段抛出 TypeError。来源文件同时说明修复中采用 `TYPE_CHECKING` 条件导入，以避免 `PeekaAgent` 类型提示导致循环导入。

代码变更片段（原文保留）：

**修改前：**
```python
class BaseCommand(ABC):
    """Base class for all diagnostic commands"""

    def __init__(self):
        self.name = self.__class__.__name__
```

**修改后：**
```python
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

class BaseCommand(ABC):
    """Base class for all diagnostic commands"""

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        self.name = self.__class__.__name__
        self.agent = agent
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 命令系统重构时增加 agent 传递但未更新基类 |

> 致因提交无法确定性定位；来源文件仅说明“命令系统重构时引入”。

### 复现

#### 前置条件
- Agent 在命令实例化时传递 `agent`
- `BaseCommand` 仍为旧无参构造

#### 步骤
1. 启动 peeka attach。
2. 执行任意需要访问 agent 的命令。
3. 观察异常信息。

#### 预期行为
命令应正常实例化并执行。

#### 实际行为
抛出 TypeError：`BaseCommand.__init__() takes 1 positional argument but 2 were given`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `c20789c` | 未提供 | 2026-02-05 | fix: BaseCommand should accept agent parameter |

#### 变更内容
更新 `BaseCommand` 构造函数签名为可选 `agent` 参数，并保存至实例属性；配合 `TYPE_CHECKING` 条件导入 `PeekaAgent`。

#### 验证
- 所有命令可正常实例化。  
- 子类可以通过 `self.agent` 访问 agent。

### 影响

- **受影响用户**：执行依赖 agent 的命令用户。
- **持续时间**：从命令系统重构引入不兼容到 `c20789c` 修复提交。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 命令系统重构引入参数契约不一致 |
| 2026-02-05 | 执行命令触发 TypeError |
| 2026-02-05 | 修复提交：`c20789c` |
| 2026-02-05 | 命令实例化与 agent 访问验证通过 |

### 经验教训

#### 做得好的方面
- 问题定位集中在基类构造函数，修复高效。
- 修复同时处理了类型提示循环导入风险。

#### 可以改进的方面
- 基类构造签名与调用方未同步演进。
- 缺少命令系统构造兼容性测试。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 基类构造函数变更时同步检查调用方/子类兼容性 | P1 | 待处理 |
| 为命令实例化路径补充契约回归测试 | P1 | 待处理 |

### 预防

- **立即执行**：保持 `BaseCommand` 签名与 Agent 调用参数一致。
- **短期**：命令系统增加实例化兼容性测试。
- **长期**：重构流程中固化基类契约检查。

### 参考

- 修复 PR/提交：`c20789c fix: BaseCommand should accept agent parameter`
- 相关 issue：未提供

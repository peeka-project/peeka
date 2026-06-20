# ADR 0001: ResourceOwningCommand 抽象

- 状态：Accepted
- 日期：2026-06-20
- 决策者：peeka 维护者
- 相关计划：`.sisyphus/plans/resource-owning-command-abc.md`（执行记录）

## 上下文

peeka 通过 `BaseCommand` 子类实现各项诊断功能。其中部分命令（`monitor`、`top`、`memory`）会在目标进程内创建持久副作用：注入装饰器、启动后台采样线程、开启 `tracemalloc`、保留快照列表等。这些资源必须在 `detach` 或 `reset` 时被显式清理，否则会导致：

- 函数对象被永久包装，影响目标程序行为
- 后台线程持续运行，CPU 占用不释放
- `tracemalloc` 持续追踪，造成内存监控泄漏
- 快照列表无限增长

### 之前的实现（不可持续）

`peeka/core/agent_control/lifecycle.py` 通过硬编码命令名调度清理：

```python
# 旧实现示意
if "monitor" in agent.command_handlers:
    agent.command_handlers["monitor"]._stop_all_monitored()
if "top" in agent.command_handlers:
    agent.command_handlers["top"]._stop_sampling()
# ...
```

### 反复发生的回归

历史记录（前置 plan `lifecycle-cleanup-hardening` 的 RCA）显示，每次新增有副作用的命令时：

1. 作者实现 `execute()` 并注册到 `_COMMAND_REGISTRY`
2. 忘记在 `lifecycle.py` 添加对应的清理分支
3. 资源泄漏在生产环境被发现
4. 修复方式：再加一个硬编码 `if` 分支

这个模式无论补多少代码评审、多少测试都治标不治本，**因为"忘记登记"在结构上没有任何机制阻止**。

## 决策

引入三层防护机制，使"忘记清理资源"在结构上不可能：

### 1. ABC 契约层 — `ResourceOwningCommand`

新增 `peeka/commands/resource_owning.py`：

```python
class CleanupScope(str, Enum):
    DETACH_ONLY = "detach_only"
    DETACH_AND_RESET = "detach_and_reset"


class ResourceOwningCommand(BaseCommand, ABC):
    is_resource_owner: bool = True
    cleanup_scope: CleanupScope  # 子类必须设置

    @abstractmethod
    def stop_active_resources(self, pattern, reason) -> Dict[str, Any]: ...

    @abstractmethod
    def list_active_resources(self) -> Dict[str, Any]: ...
```

效果：任何资源持有命令如果不实现两个 abstract 方法 → 实例化即 `TypeError`。

### 2. 显式声明层 — `BaseCommand.is_resource_owner`

`BaseCommand` 默认 `is_resource_owner: bool = False`。所有具体子类**必须在 `cls.__dict__` 里显式重新声明**该值（继承不算），由枚举测试 `test_all_concrete_basecommand_subclasses_explicitly_declare_is_resource_owner` 强制。

效果：新增命令时作者必须主动表态"我是不是资源 owner"，无法默默继承默认值蒙混过关。

### 3. 动态发现层 — `lifecycle.py` 零硬编码

`stop_resource_owners_for_detach` / `stop_resource_owners_for_reset` 只通过运行时类型检查发现 owner：

```python
for handler in list(agent.command_handlers.values()):
    if not isinstance(handler, ResourceOwningCommand):
        continue
    if handler.cleanup_scope not in (CleanupScope.DETACH_ONLY, CleanupScope.DETACH_AND_RESET):
        continue  # detach 路径
    handler.stop_active_resources(pattern=None, reason="detach")
```

效果：新增 `ResourceOwningCommand` 子类**自动**进入清理路径，无需修改 `lifecycle.py`。`test_lifecycle_module_has_no_hardcoded_command_names` 通过字面量扫描禁止 `"monitor"` / `"top"` / `"memory"` 出现在 `lifecycle.py`，永久关闭硬编码退路。

### 测试防御层

6 个枚举测试在 CI 直接拦截违规：

| 测试 | 拦截的违规 |
|---|---|
| `test_abstract_subclass_raises_typeerror_on_instantiation` | 子类未实现 abstract 方法 |
| `test_all_concrete_basecommand_subclasses_explicitly_declare_is_resource_owner` | 子类未在 `cls.__dict__` 显式声明 |
| `test_bidirectional_consistency_is_resource_owner_and_resource_owning_command` | `is_resource_owner` 与是否继承 ABC 不一致 |
| `test_resource_owning_subclasses_have_valid_cleanup_scope` | `cleanup_scope` 不是合法枚举值 |
| `test_resource_owning_subclasses_can_be_instantiated` | ABC 链路存在抽象漏洞 |
| `test_lifecycle_module_has_no_hardcoded_command_names` | `lifecycle.py` 出现硬编码命令名 |

## 边界（哪些**没**纳入抽象）

显式排除以下范围，避免抽象过度泛化：

| 范围 | 原因 |
|---|---|
| streaming 命令（`watch` / `trace` / `stack`） | 走 `ProbeContext.__exit__` 边界，由 probe 自身管理生命周期。强行套 ABC 会破坏现有职责分离 |
| `agent.stop()` 路径 | 进程终止时操作系统会回收资源，"忘记登记"风险显著低于在线 detach/reset |
| 静态类型检查（mypy/pyright） | 项目约束不引入新依赖。ABC 强制在运行时（实例化时）触发，已经足够 |

## 后果

### 正面

- **结构性消除**"忘记登记"类回归
- 新资源 owner 加入 detach/reset 路径**零成本**
- 抽象边界清晰：streaming 与 resource-owning 两条独立轨道
- 测试层显式枚举所有契约，CI 失败信息精准

### 负面 / 妥协

- 增加一层抽象，新贡献者需要先理解 `CleanupScope` 二选一
- 枚举测试扫描需要 `module.startswith("peeka.commands")` 过滤来排除 test fake 类，是个轻微的测试基础设施怪味
- `MemoryCommand` 引入 `_started_by_peeka` state machine 区分"peeka 启动的 tracemalloc"vs"外部启动的 tracemalloc"，提高了局部复杂度（但修复了静默泄漏，值得）

### 中性

- `TopCommand.stop_active_resources` 的返回类型从 `stopped: bool` 统一为 `stopped: list`，API 形状对齐，对调用方是平滑改进
- `lifecycle.py` 从命令式硬编码变成数据驱动遍历，行数减少但抽象层级提高

## 后续工作（不在本 ADR 范围）

如果未来 streaming 路径出现类似的"忘记清理"模式，可以考虑：

1. 为 `ProbeContext` 设计平行的 ABC 抽象
2. 让两套抽象共享更上层的 `Cleanupable` 接口

但目前 streaming 路径有 `ProbeContext.__exit__` 自动清理，**没有**已知回归证据，**不**应预先抽象。

## 参考

- 实现 commits：`51274e7` → `6a615d8`（共 15 个语义化提交）
- 关键源文件：
  - `peeka/commands/resource_owning.py`
  - `peeka/commands/base.py`
  - `peeka/core/agent_control/lifecycle.py`
- 关键测试：
  - `tests/test_resource_owning_contract.py`
  - `tests/test_lifecycle_helper.py`
  - `tests/test_memory.py::TestMemoryCleanupContract`

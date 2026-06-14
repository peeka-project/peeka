# Peeka Wrapper Ownership Design Contract

**English Summary**: This document defines the ownership and restoration invariants for Python function wrappers in Peeka. The core principle is that `__wrapped__` is a metadata convention, not a proof of ownership. Peeka must only strip wrappers it explicitly owns (verified via internal metadata), ensuring user decorators (like `@lru_cache`) are preserved during uninstrumentation.

---

## 1. `__wrapped__` 是元数据，不是所有权证明

在 Python 装饰器生态中，`functools.wraps` 会自动设置 `__wrapped__` 属性。这是一个通用的元数据约定，意为“此对象包装了另一个可调用对象”。

**Peeka 不变量**：
- 存在 `__wrapped__` 属性**不能**证明该包装层属于 Peeka。
- 用户装饰器（如 `@lru_cache`）、第三方库或标准库装饰器都会设置此属性。
- Peeka 严禁仅根据 `__wrapped__` 链的存在就盲目执行 `unwrap` 或将其作为恢复（restore）目标。

## 2. Restore 不变量

当 Peeka 停止监控（monitor stop）或解除注入（uninject）时，必须确保恢复后的函数身份是正确的。

**Peeka 不变量**：
- Peeka 必须恢复到进入本次注入/监控周期之前的原始状态。
- 除非 Peeka 自身的 Injector 元数据（`instrumented` 字典）能够证明某个可调用对象是一个当前活跃的 Peeka 包装器，否则不允许跳过该层。
- 只有被 Peeka 显式拥有的包装器才可以被“剥离”；所有非 Peeka 拥有的层级必须原样保留。

## 3. 已审计安全的保留点

代码库中存在少量已审计且确认安全的 `__wrapped__` 或 `inspect.unwrap` 访问点。这些位置不属于危险的恢复逻辑。

- **`peeka/core/instrumentation/registry.py` (`_live_previous_probe_wrapper`)**：
    该逻辑仅用于遍历 Peeka 活跃包装器链，并在无法证明所有权时回退到 `root_original`。它不驱动任意的用户装饰器剥离。
- **`peeka/core/instrumentation/watch.py` (`inspect.unwrap`)**：
    用于分类被监听函数（如处理 stop lambda 场景），不用于决定恢复替换的目标。

这些点目前被视为安全并保留。

## 4. 新增 `__wrapped__` 访问的审查规则

为了防止 P1 级别回归，任何新增的涉及 `__wrapped__` 属性或 `inspect.unwrap` 的代码必须遵循以下流程：

1. **所有权验证**：必须说明该访问如何区分 Peeka 包装器与用户包装器。
2. **测试门禁**：必须将新增的访问位置添加到 `tests/test_wrapped_access_gate.py` 的允许列表中（如果该测试存在）。
3. **显式注释**：代码中必须包含注释，解释为何该 `__wrapped__` 访问不会导致用户装饰器被错误剥离。

## 5. 历史教训（根因回顾）

**问题背景**：
在旧版 `monitor stop` 逻辑中，Peeka 会沿着 `__wrapped__` 链递归查找，直到找到一个没有 `__wrapped__` 的函数或 Peeka 认为的“原始函数”。

**后果（P1 Bug）**：
如果用户使用了 `@lru_cache` 或自定义装饰器，Peeka 在停止监控时会错误地将函数恢复为最内层的原始函数，从而剥离了用户所有的包装层。这导致了缓存行为失效以及 `cache_info()` 等方法从模块命名空间中消失。

**修复方案**：
引入了 `_known_peeka_root_for_wrapper()` 检查。所有权证明现在依赖于 Injector 记录的元数据，而不是通用的 `__wrapped__` 链。通过 `owned_root_original` 确保了即使在多层装饰场景下，Peeka 也只处理自己创建的那一层。

# ADR 0003: 包资源解析与调试器静默失败防护

- 状态：Accepted
- 日期：2026-07-01
- 决策者：peeka 维护者
- 相关计划：`.sisyphus/plans/attach-resource-hardening.md`

## 上下文

`_attach.gdb` 曾在 `peeka/core/attach.py` 时代通过 `os.path.dirname(__file__)` 在 `injectors.py` 中拼路径定位。随后模块迁移到 `peeka/core/attach_workflow/injectors.py`，但资源文件仍然留在包内原位置，导致相对 `__file__` 的目录解析失真，最终找不到真正的脚本资源。

这次回归的危险点不只是“路径错了”，而是调试器本身并不会立刻失败：

- GDB 只输出 warning
- 退出码仍然是 `0`
- 上层 `wait_agent_ready` 继续等待
- 最终表现为超时，而不是明确报错

也就是说，问题属于“资源解析错误 + 调试器静默失败”组合回归。仅靠 exit code 不能发现，必须读取调试器输出并识别致命模式。

## 决策

### 1. 包资源统一通过 `importlib.resources` 解析

所有包内资源必须通过 `peeka/core/resources.py` 提供的接口访问：

- `core_resource_path`
- `require_core_resource`

禁止在包内代码里使用 `__file__` 或 `dirname(__file__)` 定位数据文件。

### 2. 禁止用 `__file__` 寻址包数据

任何 package data、脚本模板、注入辅助文件，都必须走资源 API，而不是依赖源码布局。这样可以保证：

- 模块重排不影响资源定位
- wheel / zip / 可编辑安装行为一致
- attach 工作流不会因目录迁移而脆弱

### 3. GDB / LLDB 必须扫描输出，不只看退出码

调试器调用必须对 `stdout + stderr` 做合并检查，识别：

- 致命模式
- 已知 benign/warning 模式
- 需要升级为失败的提示

仅检查 exit code 不足以发现“warning 但实际未注入成功”的场景。

### 4. GDB 与 LLDB 路径必须对称

两个后端都要同时具备：

- 预检（resource presence / executable availability / attach readiness）
- 输出模式检测（fatal / benign）
- 统一失败语义

不能只修一个后端，另一个继续靠 exit code 兜底。

### 5. attach 路径改动必须带容器 smoke test

凡是影响 attach / injector / debugger script resolution 的改动，都必须包含容器 smoke test，至少覆盖 Python 3.8 路径。

## 边界

本 ADR **不** 覆盖：

- PEP 768 原生路径
- 与 attach 无关的普通 `__file__` 使用
- 业务代码中不涉及包资源定位的本地文件读取

## 后果

### 正面

- 包资源定位与源码布局解耦
- 模块迁移不会再破坏脚本注入
- 调试器 warning 不再伪装成成功
- GDB / LLDB 的失败语义更一致
- attach 回归更容易被测试和容器验证捕获

### 负面 / 妥协

- 资源访问代码稍微更抽象
- 需要维护调试器输出模式表
- attach 失败路径会更早暴露，短期内可能增加错误信息量

### 中性

- `resources.py` 会成为包资源访问的单一入口
- attach 相关测试会更偏向“行为验证”而不是“exit code 验证”

## 代码评审检查清单

未来任何 attach / resource PR 必须确认：

- [ ] 没有新增 `__file__` / `dirname(__file__)` 寻址包数据
- [ ] 新增资源通过 `core_resource_path` / `require_core_resource` 获取
- [ ] GDB / LLDB 输出都检查了 `stdout + stderr`
- [ ] 致命模式与 benign 模式都有覆盖
- [ ] GDB 与 LLDB 的错误处理语义一致
- [ ] 相关测试覆盖了资源缺失与静默失败场景
- [ ] 至少有一个容器 smoke test 覆盖 attach 路径
- [ ] 未把 PEP 768 路径混入本次修复边界

## 参考

- commits: `f497efc`, `6e7aedc`, `cd6515b`
- 关键文件:
  - `peeka/core/resources.py`
  - `peeka/core/attach.py`
  - `peeka/core/attach_workflow/injectors.py`
- 关键测试:
  - `tests/test_core_resources.py`
  - `tests/test_gdb_script_injection.py`
  - `tests/container/test_attach_smoke_py38.py`

# Peeka 路线图

Peeka 的定位是面向在线 Python 进程的生产可用运行时诊断工具。
这份路线图用于表达方向，不是严格的发布承诺。如果附加稳定性、安全性或平台兼容性出现更高优先级问题，计划会调整。

## 方向原则

- 优先缩短从“发现异常”到“定位原因”的时间，而不是单纯增加命令数量。
- 优先建设生产环境可用、可恢复、可解释的诊断工作流。
- 优先优化完整链路：`attach -> 缩小范围 -> 采集证据 -> reset -> detach`。

## 标签说明

- `Attach`
- `Observation`
- `TUI`
- `CLI`
- `Docs`
- `Automation`
- `Platform`
- `Safety`

## 近期计划

- `CLI` `Safety` `peeka doctor`
  在用户执行附加前检查 Python 版本支持、ptrace 权限、GDB 或 LLDB 可用性、容器限制和缺失依赖，减少 attach 失败后的试错成本。
- `Observation` `CLI` `TUI` 条件表达式辅助与校验
  为 `watch`、`trace`、`stack` 的 `--condition` 增加变量提示、示例、预检查和错误反馈，降低表达式门槛。
- `Automation` `Docs` 诊断 recipes
  提供可复用的诊断预设，例如“慢请求排查”“内存泄漏排查”“死锁定位”，最好支持项目级配置文件。
- `TUI` 连接状态与会话可见性增强
  在固定状态区展示附加方式、目标 Python 版本、连接健康度、活跃观测项和当前会话状态。
- `Observation` `CLI` `TUI` 流式结果搜索、过滤与导出
  让实时输出更容易搜索、冻结、筛选和导出，便于事故复盘和缺陷复现。
- `Docs` 框架与部署场景文档
  补齐 FastAPI/Uvicorn、Gunicorn 多 worker、Celery、Docker 等常见长期运行服务的使用指南。

## 中长期计划

- `Automation` 已保存会话与证据包
  将 trace、线程栈、top 快照、memory diff 打包为可共享的诊断产物。
- `Platform` 多进程诊断
  支持针对 worker 型进程组的发现、附加和跨进程导航。
- `Platform` 远程目标支持
  支持通过 SSH、容器内代理或轻量 relay 诊断远端进程，而不只是假设本机 Unix socket。
- `Observation` 异步与跨线程关联
  在线程池和异步任务边界保留更多因果上下文，提升复杂并发问题的可解释性。
- `Automation` CI 与断言模式
  将运行时诊断能力沉淀为可重复执行的检查，让 CI 能自动失败或自动附带诊断证据。

## 已完成或已具备

- `Attach` Python 3.14+ 基于 PEP 768 的附加能力，以及旧版本的调试器降级方案。
- `Observation` `watch`、`trace`、`stack`、`monitor`、`top`、`memory`、`inspect`、`thread`、`logger`、`sc`、`sm` 等核心命令集。
- `CLI` 面向管道和 `jq` 的 JSONL 输出。
- `TUI` 包含进程选择、帮助页、主题和自动补全的多视图界面。
- `Automation` 从启动即注入的 `run` 工作流，以及 `reset`、`detach` 的恢复路径。

## 低优先级

- 只改善观感、但不提升可用性的主题和视觉微调。
- 不能改善端到端诊断体验的单点型新命令。

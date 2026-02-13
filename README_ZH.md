# Peeka

[English Documentation](README.md) | [📚 完整文档](https://wwulfric.github.io/peeka/)

基于 Python 3.14 远程调试协议（PEP 768）的运行时诊断工具，提供类似 Java Arthas 的非侵入式函数观测能力。

## 核心特性

- **非侵入式**：无需修改目标代码，运行时动态注入观测逻辑
- **实时诊断**：毫秒级数据传输延迟，流式观测数据推送
- **生产可用**：性能开销 < 5%，完善的异常捕获和恢复机制
- **安全可靠**：基于 simpleeval 的安全表达式过滤（AST 白名单，阻止代码注入）
- **条件过滤**：灵活的过滤语法（参数、返回值、执行时间等）

## 快速开始

### 安装

```bash
pip install peeka
```

### 基本使用

```bash
# 附加到目标进程
peeka-cli attach <pid>

# 观测函数调用
peeka-cli watch "module.Class.method" --times 5

# 条件过滤
peeka-cli watch "module.Class.method" --condition "len(params) > 2"
```

## 命令参考

| 命令 | 功能 | 文档链接 |
|------|------|----------|
| `attach` | 附加到目标进程 | [📖 文档](https://wwulfric.github.io/peeka/commands/attach.html) |
| `watch` | 观测函数调用 | [📖 文档](https://wwulfric.github.io/peeka/commands/watch.html) |
| `trace` | 追踪函数调用链 | [📖 文档](https://wwulfric.github.io/peeka/commands/trace.html) |
| `stack` | 追踪函数调用栈 | [📖 文档](https://wwulfric.github.io/peeka/commands/stack.html) |
| `reset` | 重置增强 | [📖 文档](https://wwulfric.github.io/peeka/commands/reset.html) |
| `logger` | 动态调整日志级别 | [📖 文档](https://wwulfric.github.io/peeka/commands/logger.html) |
| `monitor` | 性能统计监控 | [📖 文档](https://wwulfric.github.io/peeka/commands/monitor.html) |
| `memory` | 内存分析 | [📖 文档](https://wwulfric.github.io/peeka/commands/memory.html) |
| `inspect` | 运行时对象检查 | [📖 文档](https://wwulfric.github.io/peeka/commands/inspect.html) |
| `sc` / `sm` | 搜索类/方法 | [📖 文档](https://wwulfric.github.io/peeka/commands/search.html) |

详细命令使用见 [命令参考文档](https://wwulfric.github.io/peeka/commands/)。

## 文档

- [📚 完整文档](https://wwulfric.github.io/peeka/) - 完整的文档站点
- [快速开始](https://wwulfric.github.io/peeka/quickstart.html) - 快速上手指南
- [架构设计](docs/ARCHITECTURE.md) - 系统架构和设计
- [使用示例](https://wwulfric.github.io/peeka/examples.html) - 实际使用示例
- [与 Arthas 对比](https://wwulfric.github.io/peeka/comparison.html) - 功能对比
- [故障排除](https://wwulfric.github.io/peeka/troubleshooting.html) - 常见问题和解决方案
- [开发指南](AGENTS.md) - 开发者指南

## Python 版本支持

| 版本  | 附加机制          | 要求                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | 无                             |
| 3.9-3.13 | GDB + ptrace 降级方案     | GDB, python3-dbg, CAP_SYS_PTRACE |

## 许可证

MIT License

## 致谢

- 灵感来源：[Alibaba Arthas](https://github.com/alibaba/arthas)
- 安全评估：[simpleeval](https://github.com/danthedeckie/simpleeval)
- 远程调试协议：[PEP 768](https://peps.python.org/pep-0768/)

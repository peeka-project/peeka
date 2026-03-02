---
layout: default
title: 与 Arthas 对比
nav_order: 7
---

# 与 Arthas 对比
{: .no_toc }

Peeka 的设计深受 [Alibaba Arthas](https://github.com/alibaba/arthas) 启发，为 Python 生态系统带来了类似的诊断能力。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 设计理念对比

| 维度 | Peeka | Arthas |
|------|-------|--------|
| **目标语言** | Python | Java |
| **附加机制** | PEP 768 / GDB + ptrace | Java Attach API |
| **通信协议** | Unix Domain Socket | Netty + HTTP |
| **命令接口** | CLI + TUI | CLI + Web UI |
| **输出格式** | JSONL | Text + JSON |
| **安全机制** | simpleeval | OGNL + sandbox |

---

## 功能对比

### ✅ 已实现的 Arthas 功能

| 功能 | Peeka | Arthas | 说明 |
|------|-------|--------|------|
| **watch 命令** | ✅ | ✅ | 观测函数调用、参数、返回值 |
| 观测点控制 | `-b/-e/-s/-f` | `-b/-e/-s/-f` | AtEnter/AtExit/AtExceptionExit |
| 条件过滤 | `--condition-express` | `--condition-express` | 支持表达式过滤 |
| 耗时过滤 | `cost > 100` | `#cost>100` | 基于执行时间过滤 |
| 输出字段 | `params/returnObj/throwExp/cost` | 相同 | Arthas 兼容字段名 |
| **trace 命令** | ✅ | ✅ | 追踪函数调用链和耗时 |
| 调用树展示 | ✅ 树形结构 | ✅ 树形结构 | 可视化调用关系 |
| 深度限制 | `-d, --depth` | `-n` | 控制追踪深度 |
| 跳过内置函数 | `--skip-builtin` | `--skipJDKMethod` | 减少输出噪音 |
| 最小耗时 | `--min-duration` | - | 过滤耗时较小的调用 |
| **stack 命令** | ✅ | ✅ | 捕获函数调用栈 |
| 条件过滤 | ✅ | ✅ | 支持条件表达式 |
| **monitor 命令** | ✅ | ✅ | 性能统计监控 |
| 周期统计 | ✅ | ✅ | 定期输出统计数据 |
| **logger 命令** | ✅ | ✅ | 动态调整日志级别 |
| 查看 logger | ✅ | ✅ | 列出所有 logger |
| 修改级别 | ✅ | ✅ | 运行时修改日志级别 |
| **sc/sm 命令** | ✅ | ✅ | 搜索类和方法 |
| 模式匹配 | ✅ | ✅ | 支持通配符搜索 |
| **memory 命令** | ✅ | ✅ | 内存分析 |
| 内存概览 | ✅ | ✅ | 显示内存使用情况 |
| **inspect 命令** | ✅ | ✅ (ognl) | 运行时对象检查 |

### ✅ 已实现的功能

| 功能 | Peeka | Arthas | 说明 |
|------|-------|--------|------|
| **attach 命令** | ✅ | ✅ | 附加到目标进程 |
| **watch 命令** | ✅ | ✅ | 观测函数调用 |
| 观测点控制 | `-b/-e/-s/-f` | `-b/-e/-s/-f` | AtEnter/AtExit/AtExceptionExit |
| 条件过滤 | `--condition` | `--condition-express` | 支持表达式过滤 |
| 耗时过滤 | `cost > 100` | `#cost>100` | 基于执行时间过滤 |
| 输出字段 | `params/returnObj/throwExp/cost/target` | 相同 | Arthas 兼容字段名 |
| **trace 命令** | ✅ | ✅ | 追踪函数调用链和耗时 |
| 调用树展示 | ✅ 树形结构 | ✅ 树形结构 | 可视化调用关系 |
| 深度限制 | `-d, --depth` | `-n` | 控制追踪深度 |
| 跳过内置函数 | `--skip-builtin` | `--skipJDKMethod` | 减少输出噪音 |
| 最小耗时 | `--min-duration` | - | 过滤耗时较小的调用 |
| **stack 命令** | ✅ | ✅ | 捕获函数调用栈 |
| **monitor 命令** | ✅ | ✅ | 性能统计监控 |
| **logger 命令** | ✅ | ✅ | 动态调整日志级别 |
| **memory 命令** | ✅ | ✅ (dashboard) | 内存分析 |
| 内存概览 | ✅ | ✅ | 显示内存使用情况 |
| **inspect 命令** | ✅ | ✅ (ognl) | 运行时对象检查 |
| **sc/sm 命令** | ✅ | ✅ | 搜索类和方法 |
| **reset 命令** | ✅ | ✅ (stop) | 重置增强恢复原函数 |
| **thread 命令** | ✅ | ✅ | 线程分析和线程栈 |
| **top 命令** | ✅ | ✅ (profiler) | 函数级性能采样 |
| **detach 命令** | ✅ | ✅ (quit/exit) | 安全断开连接 |

### ⏳ 计划中的功能

| 功能 | Peeka | Arthas | 优先级 | 说明 |
|------|-------|--------|--------|------|
| 通配符匹配 | 计划中 | ✅ `module.*` | 中 | 支持 glob 模式 |
| 自定义输出表达式 | 计划中 | ✅ `-x '{params, returnObj}'` | 低 | 灵活的输出格式 |
| tt 命令 | 计划中 | ✅ | 高 | 时间隧道（记录和回放） |
| profiler | 计划中 | ✅ | 高 | CPU/堆栈火焰图 |
| heapdump | 计划中 | ✅ | 中 | 堆转储分析 |

### ❌ 不适用的功能

| 功能 | Arthas | 说明 |
|------|--------|------|
| **jvm 命令** | ✅ | Python 无 JVM |
| **jad 命令** | ✅ | Python 源码通常可用 |
| **mc/retransform** | ✅ | Python 不需要字节码编译 |
| **classloader** | ✅ | Python 模块系统不同 |

---

## Python 特有优势

### 1. 原生 JSON 输出

Peeka 所有命令输出标准 JSONL 格式，便于自动化集成：

```bash
# Peeka - 直接输出 JSON
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# Arthas - 需要额外处理文本输出
watch module.func -x 2 | grep "result" | awk '{print $3}'
```

### 2. simpleeval 安全沙箱

条件表达式使用 AST 白名单，完全防御代码注入：

```python
# ✅ Peeka - 安全评估
--condition "params[0] > 100 and cost > 50"

# ⚠️ Arthas - OGNL 可能的安全风险
--condition-express '#cost > 50'
```

### 3. Python 3.12+ 性能优化

trace 命令使用 `sys.monitoring` API，性能开销极小：

| Python 版本 | 实现 | 开销 |
|------------|------|------|
| 3.12+ | `sys.monitoring` | < 5% |
| 3.9-3.11 | `sys.settrace` | < 20% |
| 3.14+ | PEP 768 附加 | 0% (附加开销) |

对比 Arthas：
- Java Instrumentation API：< 5% 开销
- 类似性能水平

### 4. 轻量级部署

```bash
# Peeka - pip 一键安装
pip install peeka

# Arthas - 需要下载并配置
curl -O https://arthas.aliyun.com/arthas-boot.jar
java -jar arthas-boot.jar
```

### 5. Unix Domain Socket

- 更高传输效率（无需网络协议栈）
- 更强安全性（仅限本地）
- 更简单可靠（长度前缀 + JSON）

对比 Arthas：
- Arthas 使用 Netty + HTTP（支持远程）
- Peeka 专注本地诊断（更安全）

---

## 性能对比

### watch 命令性能

| 场景 | Peeka (Python 3.12+) | Arthas (Java) |
|------|---------------------|---------------|
| 装饰器注入开销 | < 1% | < 5% |
| 每次观测开销 | ~0.1ms | ~0.05ms |
| 内存占用 | ~10MB | ~30MB |
| 启动时间 | < 1s | ~3s |

### trace 命令性能

| 场景 | Peeka (Python 3.12+) | Peeka (3.9-3.11) | Arthas (Java) |
|------|---------------------|------------------|---------------|
| 追踪开销 | < 5% | < 20% | < 5% |
| 深度 5 级 | ~0.5ms | ~2ms | ~0.3ms |
| 深度 10 级 | ~1ms | ~5ms | ~0.5ms |

### monitor 命令性能

| 指标 | Peeka | Arthas |
|------|-------|--------|
| 统计开销 | < 1% | < 1% |
| 周期响应延迟 | < 10ms | < 5ms |
| 内存占用 | ~1MB | ~2MB |

---

## 使用体验对比

### 命令对比

#### watch 命令

**Peeka**:
```bash
peeka-cli watch "app.Calculator.add" \
  --condition "params[0] > 100" \
  --times 10
```

**Arthas**:
```bash
watch com.example.Calculator add \
  '#params[0] > 100' \
  -n 10
```

#### trace 命令

**Peeka**:
```bash
peeka-cli trace "app.service.process" \
  --depth 5 \
  --min-duration 10
```

**Arthas**:
```bash
trace com.example.Service process \
  -n 5 \
  '#cost > 10'
```

### 输出格式对比

#### Peeka - JSONL

```json
{"type":"observation","func_name":"app.add","args":[1,2],"result":3,"duration_ms":0.123}
{"type":"observation","func_name":"app.add","args":[3,4],"result":7,"duration_ms":0.087}
```

**优势**:
- 机器可读
- 易于解析和过滤
- 工具链丰富（jq, python, etc.）

#### Arthas - Text

```
watch result=@ArrayList[
    @Integer[3],
    @Integer[7],
]
cost=123.45ms
```

**优势**:
- 人类可读
- 直观展示
- 适合终端查看

---

## 生态系统对比

### Peeka 生态

- **集成工具**: jq, grep, awk, python
- **可视化**: Textual TUI
- **扩展性**: Python 模块化设计
- **社区**: Python 开发者社区

### Arthas 生态

- **集成工具**: Web UI, Arthas Tunnel
- **可视化**: Web Dashboard
- **扩展性**: Java 插件机制
- **社区**: 阿里巴巴支持，Java 开发者社区

---

## 适用场景

### 选择 Peeka 的理由

1. **Python 应用** - 原生 Python 支持
2. **自动化集成** - JSONL 输出便于脚本处理
3. **轻量级部署** - pip 安装，无需 Java 运行时
4. **本地诊断** - Unix Socket 安全可靠
5. **现代 Python** - 充分利用 Python 3.12+ 新特性

### 选择 Arthas 的理由

1. **Java 应用** - 专为 Java 设计
2. **远程诊断** - 支持 Arthas Tunnel
3. **Web UI** - 图形化界面
4. **成熟稳定** - 阿里巴巴生产验证
5. **丰富功能** - tt, profiler, heapdump 等高级功能

---

## 总结

| 维度 | Peeka | Arthas |
|------|-------|--------|
| **适用语言** | Python | Java |
| **核心优势** | 轻量、JSON 输出、Python 3.12+ 优化 | 成熟、功能丰富、Web UI |
| **性能** | < 5% (3.12+) | < 5% |
| **安全性** | simpleeval (AST 白名单) | OGNL (沙箱) |
| **部署** | pip 安装 | jar 下载 |
| **学习曲线** | 中等 | 中等 |
| **社区活跃度** | 发展中 | 非常活跃 |

---

## 参考资料

- [Alibaba Arthas](https://github.com/alibaba/arthas)
- [Arthas 用户文档](https://arthas.aliyun.com/doc/)
- [Peeka GitHub](https://github.com/wwulfric/peeka)
- [PEP 768 - 安全外部调试器](https://peps.python.org/pep-0768/)

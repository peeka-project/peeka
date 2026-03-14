---
layout: default
title: TUI 使用指南
nav_order: 6
---

# TUI 使用指南
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

Peeka 提供了一个功能完整的**文本用户界面（TUI）**，基于 [Textual](https://textual.textualize.io/) 框架构建。TUI 模式提供了比 CLI 更直观的交互体验，支持实时数据流、交互式操作、彩色输出和快捷键导航。

**适用场景**：
- **交互式诊断**：需要频繁切换命令和查看实时数据
- **实时监控**：观察性能指标、日志输出、内存变化
- **可视化分析**：树形结构展示调用链、颜色编码的性能数据
- **探索式调试**：不确定使用哪个命令，通过 TUI 逐步探索

## 启动 TUI

### 方法 1：直接启动

```bash
peeka
```

### 方法 2：Python 模块方式

```bash
python -m peeka.tui
```

### 启动选项

```bash
# 使用自定义主题
peeka --theme dracula

# 列出可用主题
peeka --list-themes
```

**可用主题**：
- `default` - Textual 默认主题
- `nord` - Nord 配色方案
- `dracula` - Dracula 配色方案
- `gruvbox` - Gruvbox 配色方案
- `monokai` - Monokai 配色方案
- `solarized-light` - Solarized Light
- `solarized-dark` - Solarized Dark

## TUI 界面布局

启动 TUI 后，界面分为以下几个区域：

```
┌─────────────────────────────────────────────────────────┐
│ Header - Peeka TUI                                      │
├─────────────────────────────────────────────────────────┤
│ Process Selector / PID Status                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Tab 1  Tab 2  Tab 3  ...                               │
│ ┌─────────────────────────────────────────────────────┐ │
│ │                                                     │ │
│ │         View Content Area                           │ │
│ │                                                     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ Footer - Keybinding Hints (1)Dashboard (2)Watch (3)Trace (4)Stack (5)Monitor (6)Memory (7)Logger (8)Inspect (9)Threads (0)Top     │
└─────────────────────────────────────────────────────────┘
```

### 区域说明

- **Header**：显示 TUI 标题和当前时间
- **PID Status**：显示当前附加的目标进程 PID
- **Tab Bar**：显示所有可用的视图标签
- **View Content**：当前激活视图的内容区域
- **Footer**：显示全局快捷键提示

## 全局快捷键

| 快捷键     | 功能                | 说明                      |
|---------|-------------------|-------------------------|
| `1`     | Dashboard 视图     | 切换到仪表盘                  |
| `2`     | Watch 视图         | 切换到函数观测                 |
| `3`     | Trace 视图         | 切换到调用链追踪                |
| `4`     | Stack 视图         | 切换到调用栈捕获                |
| `5`     | Monitor 视图       | 切换到性能监控                 |
| `6`     | Memory 视图        | 切换到内存分析                 |
| `7`     | Logger 视图        | 切换到日志管理                 |
| `8`     | Inspect 视图       | 切换到对象检查                 |
| `9`     | Threads 视图       | 切换到线程管理                 |
| `0`     | Top 视图           | 切换到性能分析器                |
| `?`     | Help 帮助          | 显示帮助信息（在部分视图中可用）        |
| `escape` / `q` | 返回上一级 / 退出 | Dashboard 中退出，其他视图中返回 Dashboard |

## 十大视图详解

### 1. Dashboard 视图（`1` 键）

**功能**：命令输入和执行中心

**特点**：
- 命令自动补全（支持 Tab 补全）
- 命令历史记录（↑ / ↓ 键）
- 实时执行结果显示
- 支持所有 CLI 命令

**使用方式**：
1. 输入命令（如 `watch module.func -n 10`）
2. 按 Enter 执行
3. 查看 JSON 输出结果
4. 按其他视图快捷键切换到专用视图

**适合场景**：快速执行一次性命令、查看命令输出

---

### 2. Watch 视图（`2` 键）

**功能**：观测函数调用的入参、返回值、异常、耗时

**特点**：
- 实时流式更新（观测数据持续显示）
- 支持条件过滤
- 支持观测点控制（-b / -e / -s / -f）
- 彩色输出（成功=绿色，异常=红色）
- 显示调用计数、累计耗时

**交互操作**：
- 输入函数模式（如 `module.Class.method`）
- 设置观测次数（-n 参数）
- 设置条件表达式（--condition）
- 按 Enter 启动观测
- 按 Delete 停止观测

**输出格式**：
- 表格视图：显示关键字段（params, returnObj, cost, success）
- 详细视图：JSON 格式展示完整数据

---

### 3. Trace 视图（`3` 键）

**功能**：追踪函数调用链，展示方法调用的层次关系和耗时

**特点**：
- **树形结构展示**：可视化调用层次
- **颜色编码耗时**：
  - 绿色：< 10ms
  - 黄色：10-100ms
  - 红色：≥ 100ms
- **实时流式更新**：每次调用立即显示
- **支持展开/折叠**：交互式树节点
- **深度限制**：控制追踪层数（-d 参数）

**交互操作**：
- 输入函数模式
- 设置追踪深度（默认 3 层）
- 设置跳过内置函数（--skip-builtin）
- 按 Enter 启动追踪
- 按 Delete 停止追踪
- 点击节点展开/折叠（鼠标支持）

**输出示例**：
```
`---[125.3ms] calculator.Calculator.calculate()
    +---[2.1ms] calculator.Calculator._validate()
    +---[98.2ms] calculator.Calculator._compute()
    |   `---[95.1ms] math.sqrt()
    `---[15.7ms] calculator.Logger.info()
```

---

### 4. Stack 视图（`4` 键）

**功能**：捕获函数被调用时的完整调用栈

**特点**：
- 显示完整调用链（从入口到当前函数）
- 支持条件过滤
- 实时流式更新
- 显示文件路径、行号、函数名

**交互操作**：
- 输入函数模式
- 设置堆栈深度（--depth 参数）
- 设置条件表达式
- 按 Enter 启动捕获
- 按 Delete 停止捕获

**输出格式**：
- 每次调用显示一个堆栈快照
- 从调用入口到目标函数的完整路径

---

### 5. Monitor 视图（`5` 键）

**功能**：定期输出函数性能统计（调用次数、成功率、响应时间）

**特点**：
- 周期性更新（可配置间隔）
- 显示聚合统计：
  - 总调用次数
  - 成功次数 / 失败次数
  - 平均耗时 / 最小耗时 / 最大耗时
- 支持多个函数同时监控
- 实时图表展示（可选）

**交互操作**：
- 输入函数模式
- 设置更新间隔（--interval 参数，单位：秒）
- 设置周期数（-c 参数，-1 表示无限）
- 按 Enter 启动监控
- 按 Delete 停止监控

**输出示例**：
```
Function: module.func
  Total Calls: 1523
  Success: 1500 (98.5%)
  Failed: 23 (1.5%)
  Avg Time: 12.3ms
  Min Time: 0.5ms
  Max Time: 250.8ms
```

---

### 6. Memory 视图（`6` 键）

**功能**：分析进程内存使用情况和内存分配

**特点**：
- 内存概览（总内存、RSS、堆大小）
- Top N 内存分配追踪
- 按文件 / 行号分组
- 支持手动 GC 触发
- 内存快照比较

**交互操作**：
- 查看内存概览（overview 操作）
- 启动内存追踪（start 操作）
- 查看 Top N 分配（top 操作）
- 触发垃圾回收（gc 操作）
- 停止内存追踪（stop 操作）

**常用操作快捷键**：
- `r`：刷新数据
- `g`：触发 GC
- `t`：切换追踪状态

---

### 7. Logger 视图（`7` 键）

**功能**：动态调整 Python logger 的日志级别

**特点**：
- 列出所有 logger 及其当前级别
- 运行时修改日志级别（DEBUG / INFO / WARNING / ERROR）
- 无需重启目标进程
- 支持模式匹配（如 `myapp.*`）

**交互操作**：
- 列出所有 logger（list 操作）
- 获取特定 logger 级别（get 操作）
- 设置 logger 级别（set 操作）
- 支持模式匹配（--pattern）

**输出示例**：
```
Logger: myapp.database
  Level: INFO
  Effective Level: INFO
  Handler: StreamHandler

Logger: myapp.api
  Level: DEBUG
  Effective Level: DEBUG
  Handler: FileHandler
```

---

### 8. Inspect 视图（`8` 键）

**功能**：运行时对象检查和表达式评估

**特点**：
- 执行 Python 表达式（安全沙箱）
- 检查对象属性
- 查看变量值
- 支持 `locals()` / `globals()` 检查

**交互操作**：
- 输入 Python 表达式（如 `len(my_list)`）
- 输入对象路径（如 `module.MyClass.attr`）
- 按 Enter 执行
- 查看 JSON 格式化的结果

**安全限制**：
- 禁用 `eval` / `exec` / `__import__`
- 只读访问（不能修改对象）
- 基于 `simpleeval` 的安全沙箱

---

### 9. Threads 视图（`9` 键）

**功能**：列出所有线程，检查线程状态和堆栈

**特点**：
- 实时线程列表更新
- 显示线程状态（RUNNABLE / WAITING / TIMED_WAITING）
- 显示线程 ID、名称、daemon 标志
- 点击线程查看完整堆栈
- 支持按状态过滤、按字段排序

**交互操作**：
- 查看所有线程（list 模式）
- 点击线程查看详情（detail 模式）
- 按状态过滤（RUNNABLE / WAITING / TIMED_WAITING）
- 按字段排序（tid / name / state）

**输出格式**：
- 表格视图：线程列表（tid, name, state, stack_depth）
- 详情视图：完整堆栈帧（filename, lineno, funcname, locals_keys）

**快捷键**：
- `r`：刷新线程列表
- `Enter`：查看选中线程详情
- `escape`：返回列表视图

---

### 10. Top 视图（`0` 键）

**功能**：函数级采样性能分析器（类似 `py-spy top`）

**特点**：
- 实时性能排行榜
- 显示 CPU 占用百分比（own / total）
- 显示函数耗时（own_time / total_time）
- 采样模式，性能开销 < 5%
- 支持按不同字段排序
- 颜色编码（红色=高 CPU，黄色=中等，绿色=低）

**交互操作**：
- 设置采样间隔（--interval 参数，默认 10ms）
- 设置显示周期（--cycles 参数）
- 选择排序字段（own / total / own-time / total-time）
- 按 Enter 启动分析
- 按 Delete 停止分析
- 按 `c` 清空统计（reset）

**输出示例**：
```
Function                     Own%   Total%  Own Time  Total Time
───────────────────────────────────────────────────────────────
compute_matrix              45.3%   58.7%   0.453s    0.587s
multiply                    12.8%   13.4%   0.128s    0.134s
log_result                   8.2%    8.9%   0.082s    0.089s
```

**快捷键**：
- `r`：刷新数据
- `s`：切换排序字段
- `Enter`：启动性能分析
- `Delete`：停止性能分析
- `c`：清空统计数据（reset）

---

## TUI 独有特性

相比 CLI 模式，TUI 提供以下独有特性：

### 1. 自动补全

Dashboard 输入框支持命令和参数自动补全：

- 命令名补全：输入 `wa` → 按 Tab → `watch`
- 参数补全：输入 `watch -` → 按 Tab → 显示所有参数
- 模式补全：输入 `watch mymod` → 按 Tab → 显示模块中的类和方法

**补全源**：
- 从目标进程动态获取模块、类、方法信息
- 缓存补全结果，提升响应速度

### 2. 实时流式数据

所有观测命令（watch / trace / stack / monitor / top）都支持实时流式更新：

- 数据以观测帧（OBS frame）的形式推送
- TUI 自动解析并更新界面
- 支持暂停/恢复流（部分视图）

### 3. 交互式树形结构

Trace 视图提供交互式树形结构：

- 节点可展开/折叠
- 鼠标点击支持
- 键盘导航（↑ / ↓ / Enter / ← / →）

### 4. 颜色编码

TUI 使用颜色增强数据可读性：

- **成功/失败**：绿色=成功，红色=失败
- **耗时分级**：绿色=快（<10ms），黄色=中等（10-100ms），红色=慢（>=100ms）
- **CPU 占用**：颜色强度表示 CPU 占用程度
- **日志级别**：DEBUG=蓝色，INFO=绿色，WARNING=黄色，ERROR=红色

### 5. 专用客户端

每个视图使用独立的 `StreamingAgentClient`：

- 避免数据混乱
- 支持并发操作（多视图同时工作）
- 自动重连机制

### 6. 自动跟随

Watch / Trace / Stack 视图支持自动滚动：

- 最新数据始终可见
- 可手动停止自动跟随（向上滚动）
- 手动滚动到底部恢复自动跟随

---

## TUI vs CLI 对比

| 特性             | TUI 模式                | CLI 模式                   |
|----------------|------------------------|-----------------------------|
| **交互体验**       | 实时、可视化、快捷键导航            | 命令行输入，适合脚本化              |
| **数据展示**       | 树形结构、表格、颜色编码            | 纯 JSON 输出                   |
| **实时更新**       | 自动刷新，流式推送                | 需要手动刷新或重新执行命令             |
| **自动补全**       | 支持命令、参数、模式补全            | 需要 shell 补全插件               |
| **多任务**        | 多视图并发，快速切换              | 需要多个终端窗口                  |
| **适用场景**       | 交互式诊断、实时监控、探索式调试       | 脚本化、自动化、CI/CD 集成           |
| **输出格式**       | 格式化表格、树形结构、颜色高亮         | JSONL（便于 jq / grep 处理）       |
| **学习曲线**       | 中等（需要熟悉快捷键）             | 低（标准 CLI 命令）                |
| **性能开销**       | 略高（渲染 UI）              | 低（纯数据传输）                  |

**选择建议**：
- **开发调试**：优先使用 TUI（交互体验好）
- **自动化脚本**：使用 CLI（输出格式标准化）
- **CI/CD 集成**：使用 CLI（无 TTY 环境）
- **性能分析**：两者均可（TUI 可视化更直观，CLI 便于导出数据）

---

## 使用技巧

### 1. 快速切换视图

使用数字键在视图间快速切换，无需返回 Dashboard：

```
按 2 → Watch 视图
按 3 → Trace 视图
按 5 → Monitor 视图
按 0 → Top 视图
```

### 2. 组合使用多视图

不同视图可以并发工作（每个视图使用独立客户端）：

1. 在 Watch 视图启动观测（按 `2`，输入命令，按 Enter）
2. 切换到 Monitor 视图启动监控（按 `5`，输入命令，按 Enter）
3. 切换到 Top 视图启动性能分析（按 `0`，输入命令，按 Enter）
4. 在各视图间切换查看实时数据

### 3. 使用命令历史

Dashboard 输入框支持命令历史：

- `↑`：上一条命令
- `↓`：下一条命令
- 历史记录在会话内持久化

### 4. 快速复制输出

TUI 输出可以直接复制到剪贴板：

1. 使用鼠标选择文本
2. Ctrl+C 复制（或终端默认快捷键）
3. 粘贴到其他工具（如编辑器、文档）

### 5. 主题定制

根据终端背景选择合适的主题：

```bash
# 亮色背景
peeka --theme solarized-light

# 暗色背景
peeka --theme dracula

# 列出所有主题
peeka --list-themes
```

---

## 故障排除

### 1. TUI 启动失败

**错误**：`ModuleNotFoundError: No module named 'textual'`

**解决**：
```bash
pip install peeka[tui]
# 或
pip install textual
```

### 2. 终端显示异常

**错误**：字符显示不正常、颜色丢失

**解决**：
- 确保终端支持 256 色或 24 位真彩色
- 设置环境变量：
  ```bash
  export TERM=xterm-256color
  export COLORTERM=truecolor
  ```

### 3. 快捷键冲突

**问题**：快捷键被终端或 shell 拦截

**解决**：
- 检查终端快捷键设置
- 使用 `escape` 键返回上一级（替代 `q`）
- 在 Dashboard 中输入完整命令（不使用快捷键）

### 4. 性能问题

**问题**：TUI 界面卡顿、延迟高

**解决**：
- 降低采样频率（top 命令使用更大的 `--interval`）
- 减少观测次数（watch 命令使用 `-n` 限制次数）
- 使用 CLI 模式（TUI 渲染有开销）

### 5. 连接丢失

**问题**：`Connection lost` 或 `Socket error`

**解决**：
- 检查目标进程是否仍在运行
- 检查 socket 文件（`/tmp/peeka_<pid>.sock`）是否存在
- 重新 attach 到目标进程

---

## 权限要求

TUI 模式的权限要求与 CLI 模式相同：

- **附加进程**：需要 `CAP_SYS_PTRACE` 或相同 UID
- **ptrace_scope**：需要 `ptrace_scope <= 1`（Linux）
- **Python 版本**：
  - Python 3.14+：使用 PEP 768 `sys.remote_exec()`
  - Python 3.9-3.13：需要 GDB 和 python3-dbg

详细权限要求请参考 [attach 命令文档](commands/attach.html)

---

## 总结

Peeka TUI 提供了完整的交互式诊断体验，适合需要频繁操作、实时监控和可视化分析的场景。通过 10 个专用视图和全局快捷键，开发者可以高效地诊断 Python 应用问题，无需记忆复杂的命令参数。

**最佳实践**：
- 开发环境：优先使用 TUI（交互体验好）
- 生产环境：根据需要选择 TUI（监控）或 CLI（脚本化）
- 自动化场景：使用 CLI（输出标准化，便于集成）

开始使用 TUI：
```bash
peeka
```

按 `?` 查看帮助，按 `1/2/3/4/5/6/7/8/9/0` 切换视图，开始你的诊断之旅！

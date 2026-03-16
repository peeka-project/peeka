---
layout: default
title: AI 智能体技能
nav_order: 7
---

# AI 智能体技能
{: .no_toc }

让你的 AI 编程助手学会使用 Peeka 诊断 Python 应用问题。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 什么是 peeka-diagnostics 技能

`peeka-diagnostics` 是一个 **AI Agent 技能文件**（SKILL.md），安装后你的 AI 编程助手（如 OpenCode、Cursor、Cline 等）就能：

- **自动判断**：根据问题现象（慢请求、内存泄漏、死锁等）选择正确的 peeka 命令
- **执行诊断**：通过 `peeka-cli` 附加到运行中的 Python 进程，实时采集数据
- **解析结果**：利用 JSONL 输出和 `jq` 进行结构化分析
- **按流程排查**：遵循内置的诊断 Playbook（性能分析、异常排查、内存分析、线程分析）

技能文件覆盖了 Peeka 的全部 14 个 CLI 命令，包含完整的参数说明、jq 解析方法、条件表达式语法、以及安全协议。

---

## 技能内容概览

### 诊断决策树

技能内置了症状到命令的映射表，AI 会根据现象自动选择诊断路径：

| 症状 | 推荐命令 | 目标 |
|------|---------|------|
| 响应慢 / 高延迟 | `watch` → `trace` | 定位慢调用 |
| 返回值错误 / 逻辑 bug | `watch` 观察输入输出 | 关联输入与输出 |
| 异常 / 报错 | `watch -e` → `stack` | 找到异常位置和原因 |
| 内存增长 / 泄漏 | `memory` 系列命令 | 找到内存分配和持有者 |
| CPU 高 | `top` → `trace` | 找到 CPU 热点路径 |
| 死锁 / 卡住 | `thread` → `stack` | 找到锁竞争点 |

### 4 个诊断 Playbook

| Playbook | 场景 | 核心流程 |
|----------|------|---------|
| A: 性能分析 | 接口慢、函数耗时长 | watch 过滤慢调用 → trace 分解调用树 → 定位瓶颈 |
| B: 异常排查 | 生产环境报错 | watch -e 捕获异常 → stack 获取调用栈 → 分析根因 |
| C: 内存分析 | 内存持续增长 | memory 启动追踪 → 多次快照 → diff 对比 → referrers 查引用 |
| D: 线程分析 | 死锁、线程卡住 | thread 列出状态 → 过滤 WAITING → stack 获取栈 |

### JSONL 解析能力

所有 CLI 输出都是 JSONL 格式，AI 会使用 `jq` 进行结构化分析：

```bash
# 过滤慢调用
peeka-cli watch "module.func" -n 10 | jq 'select(.type == "observation" and .cost > 100)'

# 提取异常信息
peeka-cli watch "module.func" -e -n 5 | jq 'select(.success == false) | {func: .func_name, error: .exception}'

# 内存 top 分析
peeka-cli memory --action top | jq '.data.top_allocations[:5]'
```

---

## 安装方法

### 前提条件

- 已安装 Peeka（参见[安装指南](installation)）
- 使用支持 Skill/SKILL.md 的 AI 编程助手

### 方法一：项目级安装（推荐）

将技能文件复制到项目的 `.agents/skills/` 目录中：

```bash
# 在项目根目录执行
mkdir -p .agents/skills/peeka-diagnostics

# 从 Peeka 仓库复制技能文件
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

安装后的目录结构：

```
your-project/
├── .agents/
│   └── skills/
│       └── peeka-diagnostics/
│           └── SKILL.md
├── src/
│   └── ...
└── ...
```

### 方法二：全局安装

如果你的 AI 工具支持全局技能目录（如 `~/.config/opencode/skills/`），可以安装到全局位置：

```bash
mkdir -p ~/.config/opencode/skills/peeka-diagnostics
curl -o ~/.config/opencode/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

---

## 使用方式

### OpenCode

在 OpenCode 中通过 `load_skills` 加载技能：

```typescript
task(
  category="deep",
  load_skills=["peeka-diagnostics"],
  prompt="我的 API 响应很慢，帮我用 peeka 诊断一下 PID 12345"
)
```

或直接在对话中引用：

```
@peeka-diagnostics 我的 Python 服务内存持续增长，PID 是 54321，帮我排查
```

### 其他 AI 工具

对于 Cursor、Cline 或其他支持自定义指令的 AI 工具：

1. 确保技能文件位于 `.agents/skills/peeka-diagnostics/SKILL.md`
2. AI 工具会自动发现并加载该技能
3. 当你描述 Python 诊断相关问题时，AI 会自动应用技能中的知识

### 触发关键词

以下关键词会触发 AI 使用 peeka-diagnostics 技能：

- `debug python`、`diagnose python`
- `slow app`、`memory leak`、`high CPU`
- `trace function`、`watch expression`
- `thread deadlock`、`runtime debugging`
- `profile python`、`peeka`

---

## 使用场景示例

### 场景 1：排查接口慢

> "我的 /api/users 接口响应时间从 50ms 涨到了 2s，目标进程 PID 是 12345，帮我排查"

AI 会自动：
1. `peeka-cli attach 12345`
2. `peeka-cli sc "*user*"` 发现相关类
3. `peeka-cli watch "myapp.api.users.get_users" -n 5 --condition "cost > 100"` 过滤慢请求
4. `peeka-cli trace "myapp.api.users.get_users" -n 3 -d 5` 分解调用树
5. 分析 JSONL 输出，定位瓶颈子函数
6. `peeka-cli reset && peeka-cli detach` 清理

### 场景 2：排查内存泄漏

> "我的 Python 服务运行几小时后内存从 200MB 涨到 2GB，PID 54321"

AI 会自动：
1. 附加进程并启动 tracemalloc
2. 间隔取多个快照并 diff 对比
3. 使用 `memory --action top` 找出最大分配源
4. 使用 `memory --action referrers` 追踪引用链
5. 输出分析报告和修复建议

### 场景 3：排查线程死锁

> "我的服务卡住了，所有请求都超时，PID 33333"

AI 会自动：
1. `peeka-cli thread` 列出所有线程状态
2. 过滤 `WAITING` 状态的线程
3. 获取可疑线程的详细栈信息
4. 分析锁争用情况并给出建议

---

## 技能文件维护

### 更新技能

当 Peeka 发布新版本时，更新技能文件：

```bash
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

### 自定义扩展

技能文件是纯 Markdown，你可以根据项目需求进行扩展：

- 添加项目特定的诊断模式
- 添加常用函数模式的快捷方式
- 补充项目特有的故障排除步骤

---

## 常见问题

### AI 没有使用 peeka 进行诊断？

- 确认技能文件已正确安装到 `.agents/skills/peeka-diagnostics/SKILL.md`
- 在提示中明确提到 Python 诊断、调试相关的关键词
- 确认 `peeka-cli` 已安装且可用

### AI 诊断命令执行失败？

- 检查 Peeka 是否已正确安装：`peeka-cli --help`
- 确认目标进程仍在运行：`ps -p <pid>`
- 检查权限（ptrace_scope、CAP_SYS_PTRACE）

### 技能文件在哪里可以找到？

- **GitHub 仓库**: [peeka/.agents/skills/peeka-diagnostics/SKILL.md](https://github.com/wwulfric/peeka/tree/master/.agents/skills/peeka-diagnostics)
- **Raw 下载地址**: `https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md`

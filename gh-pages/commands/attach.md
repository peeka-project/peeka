---
layout: default
title: attach
parent: 命令参考
nav_order: 1
---

# attach - 附加到目标进程
{: .no_toc }

将 Peeka Agent 注入到目标 Python 进程，建立诊断通道。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 概述

`attach` 命令是使用 Peeka 的第一步，它将 Peeka Agent 代码注入到目标进程中，并启动 Unix Domain Socket 服务器，为后续的诊断命令建立通信通道。

### 工作原理

**Python 3.14+**:
- 使用 PEP 768 的 `sys.remote_exec()` API
- 安全、高效、官方支持

**Python 3.9-3.13**:
- 使用 GDB + ptrace 机制
- 兼容性降级方案

## TUI 使用

**TUI 启动即自动附加**：直接运行 `peeka` 命令启动 TUI，会自动显示进程选择器：

1. 运行 `peeka`（无参数）
2. 在进程选择器中选择目标进程
3. 按 Enter 自动附加并进入主界面

**TUI 特性**：
- 进程列表实时刷新
- 显示进程 PID、命令行、CPU/内存使用
- 支持搜索过滤（输入关键词筛选）
- 自动验证权限（显示 PEP 768 或 GDB 可用性）

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。
---

## 语法

```bash
peeka-cli attach <pid> [options]
```

### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pid` | int | ✅ | 目标进程的 PID |

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--timeout` | 附加超时时间（秒） | 30 |
| `--socket-dir` | Socket 文件目录 | `/tmp` |

---

## 使用示例

### 基本附加

```bash
# 附加到进程 12345
peeka-cli attach 12345
```

输出：
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"status","level":"info","message":"Using PEP 768 remote_exec"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_12345.sock"}}
```

### 查找进程 PID

```bash
# 使用 ps 查找
ps aux | grep python

# 使用 pgrep
pgrep -f "my_app.py"

# 使用 pidof
pidof python3
```

### 附加并立即执行命令

```bash
# 附加后立即观测
peeka-cli attach 12345 && peeka-cli watch "app.func"
```

---

## 权限要求

### Linux 系统

#### 相同用户

最简单的方式是使用相同的用户运行 Peeka：

```bash
# 目标进程和 Peeka 都以 user1 运行
user1$ python my_app.py  # PID: 12345
user1$ peeka-cli attach 12345  # ✅ 成功
```

#### 不同用户（需要 sudo）

```bash
# 目标进程以 user1 运行，需要 sudo
user1$ python my_app.py  # PID: 12345
user2$ sudo peeka-cli attach 12345  # ✅ 成功
```

#### ptrace_scope 配置

检查当前配置：
```bash
cat /proc/sys/kernel/yama/ptrace_scope
```

| 值 | 说明 | Peeka 可用性 |
|----|------|-------------|
| 0 | 无限制（不推荐） | ✅ 所有用户可附加 |
| 1 | 仅限父子进程或 CAP_SYS_PTRACE | ✅ 推荐设置 |
| 2 | 仅限 CAP_SYS_PTRACE | ✅ 需要 sudo |
| 3 | 完全禁用 | ❌ 无法使用 |

临时修改（测试用）：
```bash
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

永久修改：
```bash
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

### Docker 容器

需要添加 `SYS_PTRACE` capability：

```bash
# 运行容器时添加
docker run --cap-add=SYS_PTRACE your-image

# docker-compose.yml
services:
  app:
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

### SELinux 系统

检查 SELinux 状态：
```bash
getenforce  # Enforcing, Permissive, Disabled
```

临时允许 ptrace：
```bash
sudo setsebool -P deny_ptrace off
```

---

## 输出格式

### 成功响应

```json
{
  "type": "success",
  "command": "attach",
  "data": {
    "pid": 12345,
    "socket": "/tmp/peeka_12345.sock",
    "python_version": "3.12.0",
    "attach_method": "remote_exec"
  }
}
```

### 错误响应

```json
{
  "type": "error",
  "command": "attach",
  "error": "Operation not permitted: ptrace access denied"
}
```

---

## 故障排除

### 错误：Operation not permitted

**原因**: 权限不足

**解决方案**:
1. 使用相同用户或 sudo
2. 检查 ptrace_scope 设置
3. 检查 SELinux 配置

```bash
# 检查进程所有者
ps -o user= -p 12345

# 使用 sudo
sudo peeka-cli attach 12345

# 放宽 ptrace 限制（测试用）
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

### 错误：Process not found

**原因**: PID 不存在或已退出

**解决方案**:
```bash
# 确认进程存在
ps -p 12345

# 重新查找 PID
pgrep -f "my_app.py"
```

### 错误：Python debugging symbols not found (Python < 3.14)

**原因**: 缺少 Python 调试符号

**解决方案**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### 错误：GDB not found (Python < 3.14)

**原因**: 未安装 GDB

**解决方案**:
```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb
```

### 错误：Timeout attaching to process

**原因**: 附加超时（可能是目标进程挂死）

**解决方案**:
```bash
# 增加超时时间
peeka-cli attach 12345 --timeout 60

# 检查目标进程状态
ps -p 12345 -o stat=
```

---

## 安全考虑

### 进程隔离

- Peeka 只能附加到本地进程
- 不支持远程附加
- Unix Domain Socket 仅限本地访问

### 权限最小化

- 生产环境建议使用相同用户运行
- 避免使用 root 权限
- 及时分离（detach）不再需要诊断的进程

### 代码注入安全

- Agent 代码只执行诊断功能
- 不会修改业务逻辑
- 所有注入都可以通过 reset 命令恢复

---

## 相关命令

- [detach]({% link commands/detach.md %}) - 从进程分离
- [watch]({% link commands/watch.md %}) - 观测函数调用
- [reset]({% link commands/reset.md %}) - 重置增强

---

## 参考资料

- [PEP 768 - 安全外部调试器](https://peps.python.org/pep-0768/)
- [Linux ptrace(2) 手册](https://man7.org/linux/man-pages/man2/ptrace.2.html)
- [Yama LSM 文档](https://www.kernel.org/doc/html/latest/admin-guide/LSM/Yama.html)

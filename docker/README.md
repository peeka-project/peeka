# Peeka Docker 测试环境

本目录包含用于验证 peeka-cli 和 peeka TUI 工具可用性的 Docker 配置。

## 镜像说明

| 镜像 | 用途 | Python版本 | 包含组件 |
|------|------|-----------|---------|
| `cli` | CLI 命令测试 | 3.12 | peeka-cli, gdb |
| `tui` | TUI 界面测试 | 3.12 | peeka, textual |
| `py314` | PEP 768 测试 | 3.14 | sys.remote_exec |
| `full` | 完整测试 | 3.12 | 全部 + pytest |

## 快速开始

### 使用 docker-compose (推荐)

```bash
cd docker

# 构建所有镜像
docker-compose build

# 运行测试
docker-compose run --rm cli   # CLI 测试
docker-compose run --rm tui   # TUI 测试
docker-compose run --rm py314 # Python 3.14 测试
docker-compose run --rm full  # 完整测试
```

### 单独构建和运行

```bash
# 从项目根目录执行

# CLI 测试
docker build -f docker/Dockerfile.cli -t peeka-cli .
docker run -it --cap-add=SYS_PTRACE peeka-cli

# TUI 测试
docker build -f docker/Dockerfile.tui -t peeka-tui .
docker run -it --cap-add=SYS_PTRACE peeka-tui

# Python 3.14 测试
docker build -f docker/Dockerfile.py314 -t peeka-py314 .
docker run -it --cap-add=SYS_PTRACE peeka-py314

# 完整测试
docker build -f docker/Dockerfile.full -t peeka-full .
docker run -it --cap-add=SYS_PTRACE peeka-full
```

## 重要说明

### ptrace 权限

Peeka 需要 ptrace 权限才能附加到进程：

```bash
# 必须添加 SYS_PTRACE 能力
docker run --cap-add=SYS_PTRACE ...
```

### TUI 终端支持

TUI 需要交互式终端：

```bash
# 必须使用 -it 参数
docker run -it --cap-add=SYS_PTRACE peeka-tui
```

### Python 3.14 说明

Python 3.14 引入了 PEP 768 (`sys.remote_exec`)，允许无需 GDB 即可附加到进程。

## CLI 测试清单

容器启动后执行以下测试：

```bash
# 1. 附加到进程
peeka-cli attach <PID>

# 2. 观测函数调用
peeka-cli watch <PID> 'demo.Calculator.add' -n 5

# 3. 观测函数入口
peeka-cli watch <PID> 'demo.Calculator.multiply' -b -n 3

# 4. 只观测异常
peeka-cli watch <PID> 'demo.Calculator.divide' -e -n 5

# 5. 条件过滤
peeka-cli watch <PID> 'demo.Calculator.add' --condition 'params[0] > 5' -n 3

# 6. 追踪调用栈
peeka-cli stack <PID> 'demo.Calculator.add' -n 2

# 7. 性能监控
peeka-cli monitor <PID> 'demo.Calculator.add' --interval 3 -c 2

# 8. 搜索类和方法
peeka-cli sc <PID> 'Calculator'
peeka-cli sm <PID> 'add'

# 9. 日志级别
peeka-cli logger <PID> --action list

# 10. 内存分析
peeka-cli memory <PID> --action overview
```

## TUI 测试清单

启动 TUI 后，验证以下功能：

- [ ] 进程列表显示 Python 进程
- [ ] 可以按 PID/命令过滤进程
- [ ] 选择进程后显示主界面
- [ ] Tab 切换正常 (D/W/S/M/E/L/I 键)
- [ ] 帮助界面显示 (? 键)
- [ ] Ctrl+Q 退出应用
- [ ] Escape 返回进程选择

## 故障排除

### 权限被拒绝

```bash
# 错误: ptrace: Operation not permitted
# 解决: 确保使用 --cap-add=SYS_PTRACE
docker run -it --cap-add=SYS_PTRACE peeka-cli
```

### TUI 显示异常

```bash
# 确保终端支持 256 色
export TERM=xterm-256color

# 确保使用交互式模式
docker run -it ...
```

### 进程附加失败

```bash
# 检查 demo 进程是否运行
ps aux | grep demo.py

# 检查 socket 文件
ls -la /tmp/peeka_*.sock
```

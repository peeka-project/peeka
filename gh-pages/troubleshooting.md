---
layout: default
title: 故障排除
nav_order: 9
---

# 故障排除
{: .no_toc }

常见问题及其解决方案。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 附加问题

### 错误：Operation not permitted

**症状**:
```
Error: Operation not permitted: ptrace access denied
```

**原因**: 权限不足，无法附加到目标进程。

**解决方案**:

#### 方案 1: 使用相同用户

```bash
# 确认目标进程所有者
ps -o user= -p <pid>

# 使用相同用户运行 Peeka
peeka-cli attach <pid>
```

#### 方案 2: 使用 sudo

```bash
sudo peeka-cli attach <pid>
```

#### 方案 3: 调整 ptrace_scope

```bash
# 检查当前设置
cat /proc/sys/kernel/yama/ptrace_scope

# 临时修改（测试用）
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# 永久修改
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### 方案 4: SELinux 配置（RHEL/Fedora）

```bash
# 检查 SELinux 状态
getenforce

# 临时允许 ptrace
sudo setsebool -P deny_ptrace off

# 或创建 SELinux 策略
```

### 错误：Process not found

**症状**:
```
Error: Process 12345 not found
```

**原因**: PID 不存在或进程已退出。

**解决方案**:

```bash
# 确认进程是否存在
ps -p 12345

# 重新查找 PID
ps aux | grep "your_app"
pgrep -f "your_app.py"
```

### 错误：Python debugging symbols not found (Python < 3.14)

**症状**:
```
Error: Python debugging symbols not found. Install python3-dbg.
```

**原因**: Python 调试符号未安装（GDB 降级方案需要）。

**解决方案**:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install python3-dbg

# RHEL/CentOS/Fedora
sudo yum install python3-debuginfo

# 验证安装
python3 -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
# 应该输出 True
```

### 错误：GDB not found (Python < 3.14)

**症状**:
```
Error: GDB not found. Please install GDB.
```

**原因**: 未安装 GDB。

**解决方案**:

```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb

# macOS
brew install gdb

# 验证版本（需要 7.3+）
gdb --version
```

### 错误：Timeout attaching to process

**症状**:
```
Error: Timeout attaching to process after 30 seconds
```

**原因**:
1. 目标进程挂死或无响应
2. 附加超时设置过短
3. 系统负载过高

**解决方案**:

```bash
# 方案 1: 增加超时时间
peeka-cli attach <pid> --timeout 60

# 方案 2: 检查进程状态
ps -p <pid> -o stat=
# D: 不可中断睡眠（可能挂死）
# R/S: 正常运行

# 方案 3: 检查系统负载
top
uptime
```

---

## 观测问题

### 观测不到数据

**症状**: watch 命令启动后，没有观测数据输出。

**原因**:
1. 函数名拼写错误
2. 函数未被调用
3. 条件表达式过于严格
4. 观测次数已达上限

**解决方案**:

#### 检查函数名

```bash
# 使用 sc/sm 搜索正确的函数名
peeka-cli sc "Calculator"
peeka-cli sm "add"

# 使用完整限定名
peeka-cli watch "demo.Calculator.add"  # ✅
peeka-cli watch "Calculator.add"        # ❌
```

#### 确认函数被调用

```bash
# 检查目标进程是否在运行
ps -p <pid>

# 检查进程日志
tail -f /var/log/your_app.log
```

#### 简化条件表达式

```bash
# 先不加条件观测
peeka-cli watch "demo.func" --times 5

# 确认有数据后再添加条件
peeka-cli watch "demo.func" --condition "cost > 100" --times 5
```

#### 增加观测次数

```bash
# 默认 -1（无限）
peeka-cli watch "demo.func"

# 或明确指定
peeka-cli watch "demo.func" --times 100
```

### 观测数据不完整

**症状**: 观测到的参数或返回值显示为 `<truncated>` 或不完整。

**原因**: 输出深度限制。

**解决方案**:

```bash
# 增加输出深度（默认 2）
peeka-cli watch "demo.func" --depth 5

# 深度说明：
# 1: 只显示类型
# 2: 显示一层结构
# 5+: 显示深层嵌套
```

### 条件表达式错误

**症状**:
```
Error: Invalid condition expression: name 'invalid_var' is not defined
```

**原因**: 条件表达式中使用了不存在的变量或不安全的函数。

**解决方案**:

#### 可用变量

```bash
# ✅ 正确的变量
params      # 参数列表
kwargs      # 关键字参数
returnObj   # 返回值
throwExp    # 异常对象
cost        # 执行时间（毫秒）
target      # 目标对象（实例方法）
```

#### 安全函数

```bash
# ✅ 允许的函数
len(), str(), int(), float(), bool()
type(), isinstance()
min(), max(), sum()

# ❌ 不允许的函数
eval(), exec(), compile()
open(), read(), write()
__import__()
```

#### 示例

```bash
# ✅ 正确
--condition "len(params) > 2"
--condition "params[0] > 100 and cost > 50"
--condition "returnObj is not None"

# ❌ 错误
--condition "my_var > 100"           # my_var 不存在
--condition "eval('1+1')"            # eval 不允许
--condition "open('/etc/passwd')"    # open 不允许
```

---

## 性能问题

### 目标进程变慢

**症状**: 附加 Peeka 后，目标进程响应变慢。

**原因**:
1. trace 命令开销过大（Python < 3.12）
2. 观测频率过高
3. 输出深度过大

**解决方案**:

#### 使用 Python 3.12+

Python 3.12+ 的 trace 命令使用 `sys.monitoring` API，开销 < 5%。

#### 限制观测频率

```bash
# ✅ 限制观测次数
peeka-cli watch "func" --times 10

# ✅ 使用条件过滤
peeka-cli watch "func" --condition "cost > 100"

# ❌ 无限观测高频函数
peeka-cli watch "high_frequency_func"
```

#### 减小输出深度

```bash
# ✅ 使用默认深度
peeka-cli watch "func"  # depth=2

# ❌ 过大的深度
peeka-cli watch "func" --depth 10
```

#### 停止不需要的观测

```bash
# 停止 watch
peeka-cli reset "func"

# 或分离进程
peeka-cli detach <pid>
```

### Peeka 客户端响应慢

**症状**: Peeka 命令执行很慢，数据传输延迟大。

**原因**:
1. 观测数据量过大
2. Unix Socket 缓冲区满
3. CPU 负载过高

**解决方案**:

```bash
# 减少数据量
peeka-cli watch "func" --times 10 --condition "cost > 100"

# 检查系统资源
top
df -h

# 清理旧的 socket 文件
rm -f /tmp/peeka_*.sock
```

---

## 输出问题

### JSON 解析错误

**症状**:
```
Error: Expecting value: line 1 column 1 (char 0)
```

**原因**: 输出包含非 JSON 内容（如 print 语句）。

**解决方案**:

```bash
# 只提取 JSON 行
peeka-cli watch "func" | grep '^{' | jq

# 或使用 Python 过滤
peeka-cli watch "func" | python -c '
import sys, json
for line in sys.stdin:
    try:
        msg = json.loads(line)
        print(json.dumps(msg))
    except:
        pass
'
```

### 输出乱码

**症状**: 输出包含乱码字符。

**原因**: 编码问题。

**解决方案**:

```bash
# 设置正确的 locale
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# 或使用 Python 处理
peeka-cli watch "func" | python -c '
import sys
for line in sys.stdin:
    print(line, end="")
' 2>&1 | tee output.log
```

---

## Docker 问题

### Docker 容器中无法附加

**症状**:
```
Error: Operation not permitted (Docker)
```

**原因**: 容器缺少 SYS_PTRACE capability。

**解决方案**:

#### docker run

```bash
docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined your-image
```

#### docker-compose.yml

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

#### Kubernetes

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    securityContext:
      capabilities:
        add: ["SYS_PTRACE"]
```

---

## TUI 问题

### TUI 显示异常

**症状**: TUI 界面显示错乱或无法正常渲染。

**原因**: 终端兼容性问题。

**解决方案**:

```bash
# 检查终端类型是否支持 256 色
echo $TERM

# 或使用 CLI 模式
peeka-cli watch "func"
```


### Docker 容器内 TUI 颜色异常

**症状**: 通过 `docker exec` 进入容器后，TUI 界面颜色丢失或 Header/Footer 与主体颜色无法区分。

**原因**: `docker exec` 不会继承宿主机的终端环境变量（`TERM`、`COLORTERM`），容器内默认 `TERM=dumb`，Textual 无法检测 truecolor 支持。

**解决方案**:

Peeka 测试镜像已内置 `TERM=xterm-256color` 和 `COLORTERM=truecolor`，`docker exec` 进入容器后 TUI 可直接使用，无需额外设置。

### TUI 卡死

**症状**: TUI 界面无响应。

**原因**:
1. 数据流过快
2. 后台线程阻塞

**解决方案**:

```bash
# 使用 Ctrl+C 退出

# 使用 CLI 替代
peeka-cli watch "func" --times 10
```

---

## 其他问题

### Socket 文件冲突

**症状**:
```
Error: Address already in use: /tmp/peeka_12345.sock
```

**原因**: 上次异常退出未清理 socket 文件。

**解决方案**:

```bash
# 删除旧的 socket 文件
rm -f /tmp/peeka_12345.sock

# 或使用不同的 socket 目录
peeka-cli attach 12345 --socket-dir /tmp/my_peeka
```

### 内存占用过高

**症状**: Peeka 或目标进程内存占用过高。

**原因**: 观测数据缓冲区过大。

**解决方案**:

```bash
# 限制观测次数
peeka-cli watch "func" --times 100

# 定期重置观测
peeka-cli reset "func"

# 或断开连接
peeka-cli detach <pid>
```

### 找不到模块

**症状**:
```
Error: No module named 'peeka'
```

**原因**: 安装问题。

**解决方案**:

```bash
# 重新安装
pip uninstall peeka
pip install peeka

# 或使用 uv
uv pip install peeka

# 验证安装
python -c "import peeka; print(peeka.__version__)"
```

---

## 获取帮助

如果以上方案都无法解决您的问题：

1. **查看日志**:
   ```bash
   peeka-cli --verbose attach <pid>
   ```

2. **GitHub Issues**:
   [https://github.com/wwulfric/peeka/issues](https://github.com/wwulfric/peeka/issues)

3. **提供信息**:
   - 操作系统和版本
   - Python 版本
   - Peeka 版本
   - 完整错误信息
   - 复现步骤

4. **社区讨论**:
   - GitHub Discussions
   - Stack Overflow (tag: `peeka`)

---

## 相关文档

- [安装指南]({% link installation.md %})
- [快速开始]({% link quickstart.md %})
- [命令参考]({% link commands/index.md %})

# Postmortem: Python 3.8 GDB injection 线程永远不调度

## 日期
2026-03-24

## 症状
- Python 3.8 Docker 容器中，peeka attach 一直超时等待 agent ready 文件（超时 30 秒）
- 同一个宿主机同一个 ptrace 设置（`ptrace_scope=0`），Python 3.12/3.14 都能成功
- 超时发生在 `_wait_for_agent_ready`，一直等不到 agent 创建 `.ready` 文件

## 根因分析
1. GDB attach 会停止整个进程
2. peeka 原方案：bootstrap 在当前线程创建一个 daemon 线程读取 agent 脚本，然后 daemon 线程 `exec` 执行 agent 初始化，bootstrap 立刻返回
3. `PyRun_SimpleString` 返回，GDB 释放 GIL、detach
4. **在 Python 3.8 中，这样创建出来的新线程永远不会被 OS 调度执行** —— 线程创建了，但代码永远不跑
5. 这个现象在新版本 Python 中不会发生，具体原因未知（猜测和 pthreads 实现/ptrace 交互变化有关），但确实稳定复现

## 错误尝试
1. **调试符号不匹配** —— 猜测 Docker Python 3.8 镜像没有匹配调试符号，系统 Python 3.9 才有。尝试重建 base 镜像从 deadsnakes 安装匹配的 Python 3.8 + libpython3.8-dbg，遇到网络问题。而且**手动调试证明就算符号正确，线程创建了还是不跑**，所以这不是根因
2. **daemon=True 导致** —— 猜测 daemon 线程不会被调度，改成 `daemon=False` 还是不行
3.** 创建线程后持有 GIL 休眠 **—— 猜测创建线程后在主线程 sleep(2)，让出 GIL 让新线程跑，还是不行。因为就算让出 GIL，GDB detach 后新线程还是不调度

## 修复方案
参考成熟 GDB 注入工具 [pyrasite](https://github.com/lmacken/pyrasite) 的做法：**不创建新线程，直接在当前上下文执行整个 agent 初始化**。

修改 `peeka/core/attach.py` 中 `_inject_via_gdb` 的 bootstrap 代码：

**原来**：
```python
bootstrap = (
    "import threading as _t; "
    f"_c = open(\\\"{escaped_script}\\\").read(); "
    "_t.Thread("
    "target=exec, args=(_c,), "
    "name='peeka-bootstrap', daemon=True"
    ").start()"
);
```

**现在**：
```python
# For Python <= 3.8, there's a bug where threads created during
# injection don't get scheduled after GDB detaches.
# So instead we just execute directly here while we still hold the GIL.
# This takes a bit longer but is guaranteed to work.
bootstrap = (
    f"_c = open(\\\"{escaped_script}\\\").read(); "
    "exec(_c);"
);
```

**为什么这样 work**:
- GDB attach 获取 GIL 后，直接读取并执行完整 agent 代码
- agent 初始化全部同步完成（创建 socket、touch ready 文件、启动 accept 线程）才返回
- GDB 释放 GIL detach 之前，一切已经准备好了
- 不需要依赖 OS 调度新线程，自然也就不会有调度问题

## 验证
- Python 3.8 attach 现在能稳定在 5 秒内成功
- ready 文件和 socket 都正确创建
- detach 工作正常
- Python 3.12/3.14 不受影响，还是走原来的路径

## 预防措施
- GDB 注入 Python 代码就照着 pyrasite 做：直接执行，不要创建新线程。更简单更可靠
- 代码已经加上注释说明这个 Python 版本相关问题
- 以后遇到类似超时问题，先检查是不是代码根本没跑，而不是符号错了

# 深入理解 Python 进程注入：从 ptrace 到 PEP 768

你有一个正在运行的 Python 进程——也许是一个生产环境中的 Web 服务，也许是一个跑了三小时的数据管道。它变慢了，或者出了某种诡异的 bug。你不能停掉它、不能重启它、不能加 print 语句。

怎么办？

答案是**进程注入**（process injection）：在不重启目标进程的前提下，将诊断代码注入到一个正在运行的 Python 解释器中。这正是 [peeka](https://github.com/peeka-project/peeka)、[memray](https://github.com/bloomberg/memray)、[pyrasite](https://github.com/lmacken/pyrasite) 等工具的核心能力。

本文将从底层原理到工程实践，系统地拆解 Python 进程注入的三代技术方案。

---

## 目录

1. [进程注入的本质问题](#1-进程注入的本质问题)
2. [第一代：pyrasite 与 GDB 直接调用 C API](#2-第一代pyrasite-与-gdb-直接调用-c-api)
3. [第二代：memray/peeka 的 dlopen + pthread 方案](#3-第二代memraypeeka-的-dlopen--pthread-方案)
4. [第三代：PEP 768 与 sys.remote_exec](#4-第三代pep-768-与-sysremote_exec)
5. [三代方案对比](#5-三代方案对比)
6. [实践中的坑](#6-实践中的坑)
7. [总结](#7-总结)

---

## 1. 进程注入的本质问题

要理解进程注入，先要理解我们面临的约束：

- **地址空间隔离**：每个进程有独立的虚拟地址空间，A 进程无法直接读写 B 进程的内存
- **GIL（全局解释器锁）**：Python 的 C API 调用几乎都需要持有 GIL
- **执行时机**：目标进程可能正处于任何状态——malloc 中途、GC 扫描中、持有 import 锁……

所以，进程注入需要回答三个问题：

1. **如何进入目标进程的地址空间？**（跨进程控制）
2. **如何安全地执行 Python 代码？**（GIL 获取）
3. **何时执行才不会崩溃？**（时机选择）

不同的工具对这三个问题给出了不同的答案。

---

## 2. 第一代：pyrasite 与 GDB 直接调用 C API

[pyrasite](https://github.com/lmacken/pyrasite)（2011 年）是最早的 Python 进程注入工具之一。它的方案简单直接：

### 原理

利用 `ptrace` 系统调用暂停目标进程，然后通过 GDB 直接调用 Python 的 C API 执行任意 Python 代码。

### 核心代码

pyrasite 的注入逻辑只有几行：

```python
# pyrasite/injector.py（简化）
gdb_cmds = [
    'call (int) PyGILState_Ensure()',
    'call (int) PyRun_SimpleString("exec(open(\\'%s\\').read())")' % filename,
    'call (void) PyGILState_Release($1)',
]
subprocess.Popen(
    'gdb -p %d -batch %s' % (pid, ' '.join(
        ["-eval-command='call %s'" % cmd for cmd in gdb_cmds]
    )),
    shell=True
)
```

翻译成人话：

1. GDB 通过 `ptrace(PTRACE_ATTACH)` 暂停目标进程
2. 在**暂停点**直接调用 `PyGILState_Ensure()` 获取 GIL
3. 调用 `PyRun_SimpleString()` 执行一段 Python 代码
4. 调用 `PyGILState_Release()` 释放 GIL
5. GDB detach，目标进程恢复执行

### ptrace 是什么？

`ptrace` 是 Linux 内核提供的进程调试接口。GDB、strace、lldb 的底层都依赖它。

```
调试器进程                    目标进程
    │                           │
    │── ptrace(ATTACH, pid) ───>│  暂停目标
    │                           │  (SIGSTOP)
    │── ptrace(PEEKTEXT) ──────>│  读内存
    │── ptrace(POKETEXT) ──────>│  写内存
    │── ptrace(GETREGS) ───────>│  读寄存器
    │── ptrace(SETREGS) ───────>│  改寄存器 → 修改执行流
    │── ptrace(CONT) ──────────>│  恢复执行
    │── ptrace(DETACH) ────────>│  脱离
```

GDB 正是利用 ptrace 的能力，在目标进程的上下文中"调用"C 函数。具体来说，GDB 会：
1. 保存目标进程当前的寄存器状态
2. 将函数参数写入寄存器/栈（遵循 ABI 调用约定）
3. 将指令指针（`rip`）设为目标函数地址
4. 设置断点用于在函数返回后接管控制
5. 恢复执行
6. 函数执行完毕后，GDB 命中断点，恢复原始寄存器

### 为什么这个方案危险？

问题出在**时机**上。当 GDB attach 并暂停目标进程时，目标可能正处于任何状态：

```
目标进程的执行时间线：
... → malloc() → [GDB 在这里暂停] → PyGILState_Ensure() → 💥

问题：malloc 内部持有 heap lock
      PyRun_SimpleString 可能也要调 malloc
      → 死锁
```

更具体地说：

| 暂停时的状态 | 调用 C API 的后果 |
|---|---|
| malloc/free 中途 | 堆锁重入 → 死锁或内存损坏 |
| GC 扫描中 | 对象引用计数不一致 → 段错误 |
| 持有 GIL | `PyGILState_Ensure()` 死锁 |
| 持有 import 锁 | 注入代码中的 import 死锁 |

pyrasite 本质上是在"碰运气"——大多数时候目标进程不在这些危险状态，所以注入成功。但在生产环境中，这种不确定性是不可接受的。

---

## 3. 第二代：memray/peeka 的 dlopen + pthread 方案

[memray](https://github.com/bloomberg/memray)（Bloomberg 开源的内存分析器）和 [peeka](https://github.com/peeka-project/peeka) 在 Python 3.8-3.13 上采用了相似的改进方案。核心思路是：**不在 ptrace 暂停点直接执行 Python 代码，而是注入一个 C 扩展，由 C 扩展在安全的时机执行代码**。

### 原理概览

```
调试器(GDB/LLDB)                目标进程
    │                              │
    │── ptrace ATTACH ────────────>│  暂停
    │── 等待安全断点命中 ─────────>│  malloc/PyMem_* 返回后
    │                              │
    │── dlopen("_inject.so") ─────>│  加载 C 扩展到目标地址空间
    │── call peeka_spawn_agent() ─>│  创建新 pthread
    │── ptrace DETACH ────────────>│  恢复执行
    │                              │
    │                              │  [新 pthread]
    │                              │  ├─ connect() 回连调试器
    │                              │  ├─ recv() 接收 agent 脚本
    │                              │  ├─ PyGILState_Ensure() ← 等待安全时机
    │                              │  ├─ PyEval_EvalCode() 执行 agent
    │                              │  └─ PyGILState_Release()
```

关键改进有三点：**安全断点**、**dlopen 注入**、**独立线程**。

### 3.1 安全断点——选择正确的时机

pyrasite 在**任意位置**暂停后就执行 C API，而 memray/peeka 等到**安全位置**才注入。

以 peeka 的 GDB 脚本为例：

```gdb
# peeka/core/_attach.gdb
b malloc
b calloc
b realloc
b free
b PyMem_Malloc
b PyMem_Calloc
b PyMem_Realloc
b PyMem_Free
b PyErr_CheckSignals
b PyCallable_Check

commands 1-10
    disable breakpoints
    delete breakpoints
    call (void*)dlopen($peeka_injector, $peeka_rtld_now)
    call (int)peeka_spawn_agent($peeka_port)
end

continue
```

解读：

1. 在 `malloc`、`PyMem_Malloc` 等函数的**入口**设置断点
2. 调用 `Py_AddPendingCall(&PyCallable_Check, 0)` 安排一个 pending call（确保 CPython 的 eval loop 会调用 `PyCallable_Check`，从而命中我们的断点）
3. 恢复执行（`continue`），等待目标进程**自然地**调用这些函数
4. 断点命中时，我们知道当前位置是**函数入口**——没有持有 heap lock、没有处于 GC 中途
5. 此时再执行 dlopen 和 spawn

这比 pyrasite 安全得多：我们不是在任意位置注入，而是在一个已知的安全点。

> **Py_AddPendingCall 的作用**：如果目标进程处于纯 Python 代码的 tight loop 中（不调用任何 C 函数），我们的 malloc/PyMem 断点可能永远不会命中。`Py_AddPendingCall` 注册的回调会在 Python eval loop 的下一个"检查点"被调用，确保断点一定会触发。

### 3.2 dlopen——将 C 扩展加载到目标进程

`dlopen` 是 POSIX 系统的动态链接器接口。通过 GDB 在目标进程中调用 `dlopen("_inject.abi3.so", RTLD_NOW)`，我们将一个编译好的 C 扩展加载到目标进程的地址空间中。

这比 `PyRun_SimpleString` 强大的关键在于：**C 代码可以创建线程，可以操作底层系统资源，不受 GIL 约束**。

peeka 在 macOS 上使用 LLDB 完成相同的工作：

```lldb
# peeka/core/_attach.lldb
expr auto $dlsym = (void* (*)(void*, const char*))&::dlsym
expr auto $dlopen = $dlsym($rtld_default, "dlopen")
expr auto $dll = ((void*(*)(const char*, int))$dlopen)($libpath, $rtld_now)
expr auto $spawn = $dlsym($dll, "peeka_spawn_agent")
p ((int(*)(int))$spawn)($port) ? "FAILURE" : "SUCCESS"
```

### 3.3 独立线程——解耦注入与执行

dlopen 之后，GDB 调用 C 扩展的 `peeka_spawn_agent()` 函数。这个函数做了什么？

```c
// peeka/core/_inject.c（核心逻辑）
__attribute__((visibility("default")))
int peeka_spawn_agent(int port)
{
    pthread_t thread;
    return pthread_create(&thread, NULL, &thread_body, (void*)(uintptr_t)port);
}
```

它**不执行任何 Python 代码**。它只是创建一个 pthread，然后立即返回。这样 GDB 可以快速 detach，目标进程恢复正常执行。

真正的工作在新线程中完成：

```c
// 新线程的执行流程
static void run_client(uint16_t port)
{
    // 1. 通过 TCP 回连调试器，接收 agent 脚本
    int sock = connect_client(port);
    recvall(sock, &script, &script_len);

    // 2. 安全地执行 Python 代码
    run_script(script, &errmsg);
}

static int run_script(const char* script, char** errmsg)
{
    // 检查 Python 是否已初始化
    if (!Py_IsInitialized()) {
        *errmsg = copy_string("Python is not initialized");
        return 0;
    }

    // 获取 GIL —— 这里会等待，直到安全
    PyGILState_STATE gstate = PyGILState_Ensure();

    // 编译并执行 agent 脚本
    int ret = run_script_impl(script, errmsg);

    PyGILState_Release(gstate);
    return ret;
}

static int run_script_impl(const char* script, char** errmsg)
{
    // 构建干净的 globals 字典
    PyObject* builtins = PyImport_ImportModule("builtins");
    PyObject* globals = PyDict_New();
    PyDict_SetItemString(globals, "__builtins__", builtins);

    // 编译 + 执行
    PyObject* code = Py_CompileString(script,
                                       "_peeka_attach_hook.py",
                                       Py_file_input);
    PyObject* mod = PyEval_EvalCode(code, globals, globals);
    // ...
}
```

**为什么独立线程更安全？**

在 pyrasite 方案中，`PyGILState_Ensure()` 在 GDB 暂停目标进程时被调用——如果暂停的线程恰好持有 GIL，这里会死锁。

在 dlopen + pthread 方案中：
1. GDB 执行 dlopen → spawn → **立刻返回** → GDB detach → 目标进程恢复
2. 新线程调用 `PyGILState_Ensure()` 时，目标进程已经在正常运行
3. `PyGILState_Ensure()` 会**等待** GIL 可用，而不是在暂停状态下强行获取

这消除了 GIL 死锁的主要原因。

### 3.4 反向连接——agent 代码的传输

一个有趣的设计细节是 agent 代码的传输。peeka 不是把代码内容写入 GDB 命令（字符串转义会很痛苦），而是采用**反向连接**：

```
[1] 调试器启动一个 TCP 服务，等待连接
[2] GDB 将端口号传给 peeka_spawn_agent(port)
[3] C 扩展中的新线程连接这个端口
[4] 调试器将 agent.py 的完整内容通过 TCP 发送过去
[5] C 扩展接收、编译、执行
```

这样做的好处是：agent 代码可以任意长、包含任意字符，不受 GDB 命令行的转义限制。

### 3.5 Legacy 回退——没有 C 扩展时怎么办？

如果 C 扩展不可用（比如没有编译、或者 GLIBC 版本不兼容），peeka 会回退到类似 pyrasite 的方式，但做了改进：

```python
# peeka/core/attach.py — _inject_via_gdb_legacy()
bootstrap = f'_c = open("{agent_script}").read(); exec(_c);'

gdb_commands = [
    'call (int) PyGILState_Ensure()',
    f'call (int) PyRun_SimpleString("{bootstrap}")',
    'call (void) PyGILState_Release($1)',
]
```

通过 `exec()` 执行文件内容而非直接内联代码，减少了转义问题。但本质上仍然有 pyrasite 的时机安全隐患，只是作为最后的回退方案存在。

---

## 4. 第三代：PEP 768 与 sys.remote_exec

Python 3.14 引入了 [PEP 768](https://peps.python.org/pep-0768/)，从**解释器层面**提供了原生的进程注入支持。这是一个根本性的范式转变。

### 核心思想

前两代方案都是从**外部**强行进入目标进程（通过 ptrace/GDB/LLDB），然后在一个"可能安全"的位置执行代码。PEP 768 的思路则是：**告诉解释器你要执行什么，让解释器自己在安全的时候执行**。

### 运作机制

```
外部进程                       目标 Python 解释器
    │                              │
    │  (1) 读 /proc/pid/maps       │
    │      定位 PyRuntime 地址       │
    │                              │
    │  (2) 读 _Py_DebugOffsets      │
    │      获取内部结构偏移量         │
    │                              │
    │  (3) 写入脚本路径到            │
    │      tstate->debugger_        │
    │        script_path            │
    │                              │
    │  (4) 设置 pending call 标志   │
    │      tstate->debugger_        │
    │        pending_call = 1       │
    │                              │
    │  (5) 设置 eval breaker        │
    │      eval_breaker |=          │
    │        PLEASE_STOP_BIT        │
    │                              │
    │  完成，无需等待                │
    │                              │
    │                              │  ... 正常执行字节码 ...
    │                              │
    │                              │  eval loop 检查 eval_breaker
    │                              │  ↓
    │                              │  发现 pending_call 标志
    │                              │  ↓
    │                              │  _PyRunRemoteDebugger()
    │                              │  ↓
    │                              │  读取 script_path
    │                              │  ↓
    │                              │  fopen + PyRun_AnyFile
    │                              │  ↓
    │                              │  执行脚本 ✅
```

CPython 内部的关键代码：

```c
// Python/ceval_gil.c
int _PyRunRemoteDebugger(PyThreadState *tstate)
{
    if (config->remote_debug == 1
        && tstate->remote_debugger_support.debugger_pending_call == 1)
    {
        tstate->remote_debugger_support.debugger_pending_call = 0;

        // 复制脚本路径（避免 race condition）
        char script_path[pathsz];
        memcpy(script_path,
               tstate->remote_debugger_support.debugger_script_path,
               pathsz);

        // 审计事件（可被安全策略拦截）
        PySys_Audit("cpython.remote_debugger_script", "s", script_path);

        // 执行脚本
        FILE* f = fopen(script_path, "r");
        PyRun_AnyFile(f, script_path);
        fclose(f);
    }
}
```

### 每个 PyThreadState 中的数据结构

```c
// Include/cpython/pystate.h
#define _Py_MAX_SCRIPT_PATH_SIZE 512

typedef struct {
    int32_t debugger_pending_call;
    char debugger_script_path[_Py_MAX_SCRIPT_PATH_SIZE];
} _PyRemoteDebuggerSupport;
```

每个线程状态增加约 516 字节，但运行时开销几乎为零——只是 eval loop 中一次分支预测极大概率命中的 `if` 检查。

### 使用方式

peeka 的实现非常简洁：

```python
# peeka/core/attach.py
def _attach_pep768(self) -> bool:
    agent_code = _read_agent_code()
    self.agent_script = self._create_agent_script(agent_code)

    # 一行搞定
    sys.remote_exec(self.pid, self.agent_script)

    # 等待 agent 就绪
    self._wait_for_agent_ready(timeout=self.READY_TIMEOUT_PEP768)
    return True
```

不需要 GDB、不需要 ptrace、不需要 C 扩展、不需要 dlopen。只需要调用者和目标进程是同一用户（或拥有 `CAP_SYS_PTRACE`），并且目标进程没有禁用远程调试。

### 安全保障

PEP 768 在安全性上的设计非常审慎：

1. **仅接受文件路径**：`sys.remote_exec` 写入的是一个**文件路径**，不是代码内容。这意味着攻击者不仅需要跨进程写内存的权限，还需要在目标进程可读的文件系统路径上放置恶意脚本
2. **审计钩子**：执行前触发 `cpython.remote_debugger_script` 审计事件，安全策略可以拦截
3. **可禁用**：`PYTHON_DISABLE_REMOTE_DEBUG` 环境变量或 `-X disable-remote-debug` 启动参数
4. **编译时可移除**：`./configure --without-remote-debug`

### 为什么 PEP 768 是本质性的进步？

| | ptrace/GDB 注入 | PEP 768 |
|---|---|---|
| **执行时机** | 取决于暂停点/断点位置 | 解释器自己选择安全检查点 |
| **GIL 处理** | 外部强制获取 | 自然持有（在 eval loop 中） |
| **运行时开销** | 无（仅 attach 时） | 接近零（一次分支检查） |
| **所需权限** | ptrace + GDB/LLDB | 同 UID 或 process_vm_writev |
| **多线程安全** | 需要 scheduler-locking | 天然安全（per-thread 标志） |
| **崩溃风险** | 存在（不安全时机） | 极低（安全检查点执行） |

---

## 5. 三代方案对比

| 方案 | 代表工具 | Python 版本 | 安全性 | 依赖 |
|---|---|---|---|---|
| GDB + PyRun_SimpleString | pyrasite | 2.4 - 3.13 | ⚠️ 可能崩溃/死锁 | GDB, ptrace |
| GDB/LLDB + dlopen + pthread | memray, peeka | 3.8 - 3.13 | ✅ 较安全 | GDB/LLDB, ptrace, C 编译器 |
| sys.remote_exec (PEP 768) | peeka, memray | 3.14+ | ✅ 安全 | 无外部依赖 |

### memray vs peeka 的容错策略

两个项目虽然共享 dlopen + pthread 的核心方案，但在**失败处理**上有本质区别：

**memray：一次选择，不回退。** memray 在启动时通过 `resolve_debugger()` 按优先级（`sys.remote_exec` > `gdb` > `lldb`）选定**一种**注入方法，此后不再切换。GDB 路径硬依赖 C 扩展（`assert injecter.exists()`），dlopen 失败直接报错，没有 legacy 回退。这是刻意的设计选择——memray 作为专业的内存分析器，对运行环境有明确的前置要求。

**peeka：逐级降级，尽力而为。** peeka 的决策树包含多层 fallback：

```python
# peeka 的 attach 决策树
if hasattr(sys, "remote_exec"):     # Python 3.14+
    → sys.remote_exec()              # 最优路径
elif _has_injector():                # C 扩展可用
    if Linux:
        try:
            → GDB + dlopen + pthread # 安全回退
        except (TimeoutError, ...):
            → GDB + PyRun_SimpleString  # 降级到 legacy
    elif macOS:
        → LLDB + dlopen + pthread
elif Linux:
    → GDB + PyRun_SimpleString       # 最后手段
else:
    → 报错
```

这种设计源于 peeka 的定位——作为通用诊断工具，它需要在各种环境下都能工作，包括 GLIBC 版本不匹配（C 扩展无法加载）或 GIL 死锁（dlopen 路径超时）等边缘情况。代价是多了一层复杂度和潜在的时机安全风险（legacy 路径），但换来了更广的兼容性。

| | memray | peeka |
|---|---|---|
| C 扩展缺失 | 硬报错 (`assert`) | 回退到 legacy GDB |
| dlopen 运行时失败 | 报错退出 | 回退到 legacy GDB |
| dlopen 后 GIL 死锁 | 超时报错 | 超时后回退到 legacy GDB |
| 设计哲学 | 明确前置要求，快速失败 | 尽力而为，逐级降级 |

---

## 6. 实践中的坑

在实际开发 peeka 的过程中，我们踩过一些有趣的坑：

### 6.1 GLIBC 版本不匹配

C 扩展 `_inject.abi3.so` 在高版本 Linux 上编译后，放到低版本容器（如 Python 3.8 的 Debian 旧镜像）中会因为 `GLIBC_2.34 not found` 而 dlopen 失败。

但 `importlib.util.find_spec()` 只检查文件是否存在，不检查能否加载：

```python
# ❌ 错误：文件存在但无法加载
def _has_injector():
    return importlib.util.find_spec("peeka.core._inject") is not None

# ✅ 正确：实际尝试 import
def _has_injector():
    try:
        import peeka.core._inject
        return True
    except (ImportError, OSError):  # OSError 捕获 dlopen 失败
        return False
```

### 6.2 GDB dlopen 后的 GIL 死锁

在 Python 3.12 上，GDB dlopen 注入的 C 扩展创建的 pthread 调用 `PyGILState_Ensure()` 时，可能因为 GDB 操作后 GIL 状态不一致而永远无法获取 GIL。

解决方案是将 dlopen 路径视为**乐观尝试**，失败后回退到 legacy GDB：

```python
if _has_injector():
    try:
        return self._inject_via_gdb_dlopen()
    except (TimeoutError, RuntimeError, OSError):
        logger.warning("GDB dlopen failed, falling back to legacy GDB")
# 控制流落入 legacy 路径
```

### 6.3 ptrace 权限

不同 Linux 发行版的默认 `ptrace_scope` 不同：

| ptrace_scope | 含义 | 默认发行版 |
|---|---|---|
| 0 | 任意同 UID 进程可 attach | Arch, RHEL |
| 1 | 仅父进程可 attach | Ubuntu, Debian |
| 2 | 仅 `CAP_SYS_PTRACE` | — |
| 3 | 完全禁止 | — |

Docker 容器默认**不授予** `CAP_SYS_PTRACE`，且 seccomp 配置也会阻止 ptrace 系统调用。需要：

```bash
docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined your-image
```

### 6.4 sys.monitoring tool_id 冲突

Python 3.12+ 的 `sys.monitoring` 只有 6 个 tool slot（0-5）。如果 coverage 工具或 debugger 已经占用了 slot 0，硬编码 `use_tool_id(0, ...)` 会抛 `ValueError`。应该遍历可用 slot：

```python
for candidate_id in range(5, -1, -1):
    try:
        sys.monitoring.use_tool_id(candidate_id, "peeka-trace")
        break
    except ValueError:
        continue
```

---

## 7. 总结

Python 进程注入经历了三代演进：

1. **直接调用 C API**（pyrasite）：简单粗暴，但有崩溃和死锁风险
2. **dlopen + pthread**（memray/peeka）：通过安全断点和独立线程显著降低风险
3. **解释器原生支持**（PEP 768）：从根本上解决问题，让解释器自己在安全时机执行代码

如果你的目标环境是 Python 3.14+，`sys.remote_exec` 是毫无争议的最佳选择。如果需要支持更老的版本，dlopen + pthread 方案提供了合理的安全性和兼容性平衡。

进程注入不是魔法，它是系统编程、编译器原理和 CPython 内部机制的交汇点。理解这些底层原理，能帮助你在遇到"进程卡死"或"注入失败"时，快速定位问题所在。

---

*本文基于 [peeka](https://github.com/peeka-project/peeka) 的实际开发经验撰写。peeka 是一个受 [Alibaba Arthas](https://github.com/alibaba/arthas) 启发的 Python 运行时诊断工具，支持 Python 3.8-3.14+。*

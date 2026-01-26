# Peeka Agent 架构设计文档

## 1. 概述

### 1.1 项目背景

Peeka 是一个基于 Python 3.14 远程调试协议（PEP 768）开发的诊断工具，其设计理念类似于 Java 生态中广泛使用的 Arthas
诊断工具。该工具旨在为 Python 开发者提供生产环境下的实时诊断能力，使得在不停止目标进程的情况下进行函数调用观测、性能分析、问题定位等操作成为可能。Peeka
的核心优势在于利用 Python 3.14 引入的 `sys.remote_exec()` 函数，实现了安全、高效的进程附加和代码注入机制，从而为 Python
应用的运行时诊断提供了可靠的技术基础。

传统的 Python 调试方法通常需要在代码中显式地插入调试语句，或者使用 IDE
的调试器进行断点调试，这些方法在开发环境中效果良好，但在生产环境中往往难以应用。生产环境的诊断需求具有其特殊性：首先，不能轻易停止运行中的服务，因为这可能影响用户体验和业务连续性；其次，问题往往是间歇性的，需要在真实的生产负载下进行观测；最后，生产环境的数据量和调用频率通常远高于开发环境，需要高效的诊断机制。Peeka
正是为了解决这些生产环境诊断难题而设计的，它提供了非侵入式的诊断能力，能够在不修改目标代码的情况下实时观测和诊断应用行为。

### 1.2 设计目标

Peeka Agent 的设计遵循以下核心目标，这些目标共同构成了整个系统的技术选型和架构决策的基础。第一个核心目标是**低侵入性**，即
Agent 的运行不应显著影响目标进程的性能和功能。根据业界经验，生产环境诊断工具的性能开销应控制在百分之五以内，否则可能导致诊断行为本身成为性能问题的来源。Peeka
通过精心设计的装饰器注入机制和观测数据缓冲策略，确保诊断操作对目标进程的影响最小化。

第二个核心目标是**高可靠性**，Agent 必须在各种异常情况下保持稳定运行，不能因为自身的错误导致目标进程崩溃或行为异常。这要求
Agent 具有完善的异常捕获和恢复机制，能够处理各种边界情况和错误状态。设计时需要特别关注资源管理问题，包括内存使用、文件描述符、线程等系统资源的正确释放，避免因资源泄漏导致的长期稳定性问题。

第三个核心目标是**实时性**，诊断数据应该能够实时传输到客户端，使开发者能够立即观察到目标进程的行为变化。这对于定位间歇性问题尤为重要，因为问题的特征可能很快消失，如果传输延迟过高，可能导致关键信息丢失。Peeka
采用基于 Unix Domain Socket 的流式通信协议，实现了毫秒级的数据传输延迟。

第四个核心目标是**可扩展性**，Agent
架构应该能够方便地支持新的诊断命令和功能扩展，而不需要大规模重构现有代码。这要求采用模块化的设计，将通信、命令执行、观测等关注点分离，通过清晰定义的接口进行交互。Peeka
的命令注册机制和观测管理器设计正是为了满足这一需求。

### 1.3 技术基础

Peeka Agent 的技术基础主要建立在 Python 3.14 引入的远程调试附加协议之上，该协议定义了一套标准化的机制，允许外部工具附加到正在运行的
Python 进程并注入执行代码。核心的 `sys.remote_exec(pid, script_path)`
函数是整个系统运作的关键，它封装了复杂的进程附加、代码注入和执行调度逻辑，为上层应用提供了简洁的接口。通过这一函数，Peeka 能够将
Agent 代码安全地注入到目标进程中，并启动监听服务准备接收诊断命令。

在通信层面，Peeka 采用 Unix Domain Socket 作为进程间通信的主要机制。相比于网络套接字，Unix Domain Socket
具有更高的传输效率和更强的安全性，因为它不需要经过网络协议栈，且仅限本地进程间使用。这对于生产环境诊断工具来说是重要的特性，既保证了数据传输的效率，又避免了网络通信可能带来的安全风险。通信协议采用长度前缀的
JSON 格式，既保证了数据的结构化特性，又能够处理变长的消息内容。

## 2. 系统架构

### 2.1 整体架构设计

Peeka Agent 的整体架构采用客户端-服务器模式，其中 Agent 运行在目标进程内部，承担服务器角色，负责接收和执行诊断命令；CLI
工具作为客户端，运行在本地机器上，负责发送命令和展示结果。这种架构设计的优势在于将诊断能力的执行环境与用户交互界面分离，使得诊断逻辑能够在目标进程的上下文中直接访问进程的运行时状态和数据。

整体架构可以分为三个主要层次：**命令入口层**负责 CLI 命令的解析和参数处理；**通信层**负责客户端与 Agent 之间的消息传递；*
*执行层**包含在目标进程内部的各个功能组件，负责实际的诊断操作。这种分层设计遵循了关注点分离的原则，每一层都有明确的职责边界，层与层之间通过定义良好的接口进行交互。这种设计不仅提高了代码的可维护性，也为后续的功能扩展奠定了基础。

```
┌─────────────────────────────────────────────────────────────────┐
│                        Peeka CLI (本地)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ CLI解析器    │→│ 命令构建器   │→│ AgentClient (Socket)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│         ↑                                                       │
│         └─ 结果展示器 (实时流式显示)                             │
└─────────────────────────────────────────────────────────────────┘
                              │ sys.remote_exec(pid, script)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     目标Python进程 (PID: xxx)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Peeka Agent                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐  │  │
│  │  │ 命令路由器   │→│ 观测管理器   │→│ 装饰器注入器       │  │  │
│  │  └─────────────┘  └─────────────┘  └───────────────────┘  │  │
│  │         ↑                                                  │  │
│  │         └─ 流式数据回传 (Socket)                           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

在数据流向方面，命令从 CLI 出发，经过序列化后通过 Unix Domain Socket 发送到目标进程中的 Agent；Agent
接收命令后，由命令路由器分发给相应的命令处理器执行；执行过程中产生的诊断数据经过处理后，通过相同的通道返回给客户端进行展示。整个过程是同步的，即客户端在发送命令后会等待响应，但对于观测类命令，会建立持久的连接以支持流式数据传输。

### 2.2 组件交互关系

Agent 内部由多个协同工作的组件构成，这些组件之间的关系可以用一个星型拓扑来描述，其中 `PeekaAgent`
类作为核心协调者，连接并管理各个子组件。这种设计的核心思想是将复杂的诊断功能分解为多个职责单一的组件，每个组件专注于特定的任务，而
Agent 核心负责协调这些组件的工作并管理它们的生命周期。

**核心协调层**由 `PeekaAgent` 类承担，它初始化并持有所有其他组件的引用，包括装饰器注入器（`DecoratorInjector`）、观测管理器（
`ObservationManager`）和命令处理器（Command Handlers）。当接收到命令时，Agent
根据命令类型将执行委托给相应的处理器，处理器在执行过程中可能需要与注入器或观测管理器交互。这种设计确保了命令处理逻辑的清晰性，每个组件只需要关注自己的职责范围。

**功能组件层**
包括装饰器注入器和观测管理器两个核心组件。装饰器注入器负责将观测逻辑动态注入到目标函数中，它实现了函数包装、引用替换和原始函数保存等关键功能。观测管理器负责管理观测数据的生命周期，包括数据的接收、缓冲、统计和分发。这两个组件紧密协作，装饰器注入器创建的包装函数在观测到函数调用时，将数据发送给观测管理器进行进一步处理。

**命令处理层**由各个具体的命令处理器组成，如 `WatchCommand`、`ThreadCommand` 等。每个处理器都实现了统一的 `BaseCommand`
接口，接收参数并返回结构化的结果。命令处理器是用户可见的功能入口，它们封装了特定诊断场景的业务逻辑，通过调用功能组件层提供的原子操作来实现复杂的诊断功能。

### 2.3 部署模型

Peeka Agent 的部署模型遵循「按需注入」的原则，即 Agent 代码不会在目标进程启动时加载，而是在需要诊断时才通过
`sys.remote_exec()` 机制注入。这种设计避免了不必要的资源占用，因为大多数时候应用并不需要诊断功能。这种按需部署的模型也与生产环境的运维实践相吻合，诊断功能仅在发现问题或需要排查性能时才会启用。

从部署视角来看，Peeka 工具由两个独立的运行实体组成：运行在本地机器上的 CLI 工具和运行在目标进程内的 Agent 代码。CLI
工具通过命令行与用户交互，解析用户的诊断请求并格式化输出结果；Agent 代码通过远程执行机制注入目标进程，独立于 CLI
工具运行。这种分离式部署使得用户可以在不同的终端或机器上操作，提高了使用的灵活性。同时，Agent 的运行不依赖于 CLI 工具的持续运行，即使
CLI 工具退出，已经注入的 Agent 仍可继续运行并缓存观测数据。

## 3. Agent 核心组件

### 3.1 PeekaAgent 主类

`PeekaAgent` 类是整个 Agent 系统的核心入口和协调者，它负责初始化各个功能组件、注册命令处理器、维护运行状态以及处理客户端连接。这个类的设计体现了「初始化-运行-清理」的生命周期管理模式，确保
Agent 能够在目标进程中正确启动、稳定运行并优雅退出。

在初始化阶段，`PeekaAgent`
的构造函数接收一个会话标识符（session_id）作为参数，这个标识符用于区分不同的诊断会话，确保多个并发的诊断操作不会相互干扰。构造函数会创建必要的状态变量，包括运行标志（running）、命令处理器字典（command_handlers）以及各个功能组件的实例。特别重要的是初始化装饰器注入器和观测管理器这两个核心功能组件，它们将在后续的诊断操作中发挥关键作用。

```python
class PeekaAgent:
    """Agent running inside target process"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.running = True
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server = None
        self.command_handlers = {}
        self.injector = DecoratorInjector(self)
        self.observer = ObservationManager(self)
        self._register_handlers()
```

启动流程由 `start()` 方法负责，它创建 Unix Domain Socket
服务器、绑定到指定的套接字路径、创建就绪标记文件，然后在一个后台线程中启动接受连接的循环。启动过程的每一步都有详细的错误处理，如果任何步骤失败，Agent
会记录错误信息并尽可能清理已分配的资源。启动完成后，Agent 会通过在临时目录中创建 `.ready`
文件来通知外部进程自己已经准备就绪，这是一个简单而有效的进程间同步机制。

连接处理是 Agent 工作的主要部分，由 `_accept_loop()`
方法在一个无限循环中执行。这个循环持续监听新的客户端连接，每收到一个连接就创建一个新的线程来处理该连接的命令请求。这种设计允许多个客户端同时连接到同一个
Agent，虽然在典型的诊断场景中通常只有一个客户端。连接处理线程会调用 `_handle_client()` 方法，该方法实现了完整的命令接收、解析、执行和响应发送流程。

命令执行的核心逻辑在 `_execute_command()` 方法中，它接收来自客户端的 JSON 命令，解析出命令类型，然后从已注册的命令处理器字典中找到对应的处理器并调用其
`execute()` 方法。执行结果被封装在统一的响应格式中，包含状态码、结果数据和可选的错误信息。这种统一的响应格式使得客户端能够以一致的方式处理所有命令的执行结果。

### 3.2 装饰器注入器

装饰器注入器（`DecoratorInjector`
）是实现函数观测功能的核心组件，它的职责是在运行时将观测逻辑动态注入到目标函数中，使得函数的每次调用都能被捕获和记录。这个组件的设计需要解决几个关键技术挑战：如何在不修改原始代码的情况下拦截函数调用；如何在注入后仍能正确执行原始函数的逻辑；以及如何在诊断结束后恢复原始函数的行为。

注入器的核心方法是 `inject()`，它接收一个函数模式字符串（如 `mymodule.MyClass.method`
）和一个观测配置字典，然后执行完整的注入流程。首先，注入器需要解析模式字符串并定位到目标函数，这涉及到 Python
的模块导入机制和属性访问逻辑。解析过程需要处理各种可能的导入模式，包括绝对导入和相对导入，以及类方法的限定名称。然后，注入器创建一个包装函数，这个包装函数在调用原始函数的同时执行观测逻辑。最后，注入器将模块中的原始函数引用替换为包装函数引用。

```python
class DecoratorInjector:
    """将观测装饰器注入到目标函数"""
    
    def __init__(self, agent):
        self.agent = agent
        self.instrumented = {}  # watch_id -> original_func
    
    def inject(self, pattern: str, watch_config: dict) -> str:
        """
        注入观测装饰器
        
        Args:
            pattern: 类名.方法名模式 (e.g., "mymodule.MyClass.method")
            watch_config: 观测配置
            
        Returns:
            watch_id: 观测ID，用于后续控制
        """
        # 解析pattern找到目标函数
        target_func = self._resolve_target(pattern)
        if not target_func:
            raise ValueError(f"Cannot find target: {pattern}")
        
        # 创建包装函数
        watch_id = self._generate_watch_id()
        wrapper = self._create_wrapper(target_func, watch_id, watch_config)
        
        # 备份原始函数
        self.instrumented[watch_id] = {
            'pattern': pattern,
            'original': target_func,
            'wrapper': wrapper,
            'module': target_func.__module__,
            'config': watch_config
        }
        
        # 替换原始函数
        self._replace_function(target_func, wrapper)
        
        return watch_id
```

包装函数的创建是注入器的另一个关键功能。`_create_wrapper()` 方法生成一个代理函数，这个函数使用 `functools.wraps`
装饰器来保留原始函数的元数据（如函数名、文档字符串等），使得调用者感知不到包装的存在。包装函数内部首先执行可选的条件检查，如果条件不满足则直接调用原始函数；否则执行原始函数并捕获其参数、返回值和执行时间等信息，然后将这些信息组装成观测数据发送给观测管理器。包装函数还处理了异常情况，确保即使原始函数抛出异常，观测数据仍能被记录。

```python
def _create_wrapper(self, func: Callable, watch_id: str, config: dict) -> Callable:
    """创建包装函数"""
    depth = config.get('depth', 2)
    condition = config.get('condition')

    safe_evaluator = None
    if condition:
        safe_evaluator = SimpleEval(allowed_attrs=BASIC_ALLOWED_ATTRS)
        safe_evaluator.parse(condition)

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()

        try:
            if safe_evaluator:
                local_vars = {'params': args, 'kwargs': kwargs}
                safe_evaluator.names = local_vars
                if not safe_evaluator.eval(condition):
                    return func(*args, **kwargs)

            result = func(*args, **kwargs)
            success = True
            error = None

        except Exception as e:
            result = None
            success = False
            error = str(e)
            raise

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000

        observation = {
            'watch_id': watch_id,
            'timestamp': time.time(),
            'func_name': f"{func.__module__}.{func.__qualname__}",
            'args': self._format_value(args, depth),
            'kwargs': self._format_value(kwargs, depth),
            'result': self._format_value(result, depth),
            'success': success,
            'error': error,
            'duration_ms': round(duration_ms, 3),
            'thread_id': threading.get_ident(),
        }

        # 发送到 Agent
        self.agent._send_observation(observation)

        return result

    return wrapper
```

为了支持诊断结束后的恢复操作，注入器维护了一个 `instrumented` 字典，记录所有已注入的观测信息，包括原始函数的引用。当需要停止观测时，可以通过
`uninject()` 方法从该字典中取出原始函数引用，恢复模块中的函数引用，从而完全撤销注入的影响。这种备份-恢复机制是确保诊断操作可逆的关键。

### 3.3 观测管理器

观测管理器（`ObservationManager`
）负责管理观测数据的整个生命周期，从接收装饰器注入器发来的观测数据，到缓冲、统计最终将数据分发给订阅者。这个组件的设计需要处理高频率的数据写入和多客户端的数据订阅，同时保持稳定的内存使用和传输性能。

观测管理器的核心数据结构包括三个部分：活动观测字典（`active_watches`）记录当前正在进行的观测及其配置和统计信息；数据缓冲区（
`data_buffer`）是一个固定大小的双端队列，用于临时存储最近的观测数据；订阅者字典（`subscribers`
）记录每个观测的订阅者及其回调函数。这种数据结构的设计使得观测管理器能够高效地处理观测数据的读写和分发。

```python
class ObservationManager:
    """管理观测数据流"""
    
    def __init__(self, agent):
        self.agent = agent
        self.active_watches = {}
        self.data_buffer = deque(maxlen=10000)
        self.subscribers = {}
        self.stats = {
            'total_observations': 0,
            'total_errors': 0,
            'start_time': None
        }
    
    def start_watch(self, watch_id: str, config: dict):
        """开始观测"""
        self.active_watches[watch_id] = {
            'config': config,
            'start_time': time.time(),
            'count': 0,
            'errors': 0,
        }
        
        if self.stats['start_time'] is None:
            self.stats['start_time'] = time.time()
    
    def receive_observation(self, observation: dict):
        """接收观测数据"""
        watch_id = observation['watch_id']
        
        # 更新统计
        self.stats['total_observations'] += 1
        if not observation['success']:
            self.stats['total_errors'] += 1
        
        if watch_id in self.active_watches:
            self.active_watches[watch_id]['count'] += 1
            if not observation['success']:
                self.active_watches[watch_id]['errors'] += 1
        
        # 缓冲
        self.data_buffer.append(observation)
        
        # 通知订阅者
        if watch_id in self.subscribers:
            for callback in self.subscribers[watch_id]:
                try:
                    callback(observation)
                except Exception:
                    pass  # 忽略订阅者错误
    
    def stop_watch(self, watch_id: str) -> dict:
        """停止观测并返回统计"""
        if watch_id not in self.active_watches:
            raise ValueError(f"Watch not found: {watch_id}")
        
        watch_info = self.active_watches.pop(watch_id)
        
        return {
            'watch_id': watch_id,
            'count': watch_info['count'],
            'errors': watch_info['errors'],
            'duration_seconds': round(time.time() - watch_info['start_time'], 3),
        }
    
    def subscribe(self, watch_id: str, callback: Callable):
        """订阅观测数据"""
        if watch_id not in self.subscribers:
            self.subscribers[watch_id] = []
        self.subscribers[watch_id].append(callback)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        elapsed = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        return {
            **self.stats,
            'active_watches': len(self.active_watches),
            'elapsed_seconds': round(elapsed, 3),
            'observations_per_second': round(
                self.stats['total_observations'] / elapsed, 2
            ) if elapsed > 0 else 0
        }
```

`receive_observation()`
方法是观测管理器接收数据的入口，它接收一个观测数据字典，更新相关的统计数据，将数据添加到缓冲区，并通知所有订阅者。数据更新包括更新全局统计计数和特定观测的计数器，缓冲区采用固定大小策略，自动淘汰最旧的数据以防止内存无限增长，订阅通知采用回调机制，每个订阅者都会收到完整的数据副本。

统计功能是观测管理器提供的重要辅助能力。`get_stats()`
方法返回一个包含当前观测状态的字典，包括总观测次数、错误次数、活动观测数量、平均观测频率等指标。这些统计信息对于评估诊断效果和发现异常模式很有帮助。例如，如果某个观测的调用频率突然下降，可能表明目标函数的调用逻辑发生了变化；如果错误率异常升高，可能表明目标函数遇到了问题。

订阅机制支持多个客户端同时订阅同一个观测的数据。流式客户端（如 `StreamingAgentClient`）通过 `subscribe()`
方法注册回调函数，当新的观测数据到达时，回调函数会被调用来处理数据。这种发布-订阅模式解耦了数据生产和数据消费，使得同一个观测数据可以被多个消费者以不同的方式处理，例如同时在控制台显示和保存到文件。

## 4. 通信协议

### 4.1 协议概述

Peeka Agent 的通信协议是整个系统正常运作的基础，它定义了客户端与 Agent 之间交换消息的格式、顺序和语义。协议设计遵循简洁、高效和可靠的原则，采用
JSON 作为数据序列化格式，Unix Domain Socket 作为传输层协议，长度前缀作为消息边界界定方式。

协议的消息格式由两部分组成：首先是四字节的网络字节序长度字段，表示后续数据部分的字节数；然后是实际的 JSON
数据。这种格式的优势在于能够正确处理包含任意字符（包括换行符）的 JSON 数据，避免了基于换行符分隔的协议可能遇到的问题。发送端在发送消息前先计算
JSON 数据的字节数，将其编码为四字节整数发送；接收端先读取四字节长度字段，然后准确读取相应字节数的数据。

消息分为三种基本类型：**命令消息**由客户端发送给 Agent，包含要执行的诊断操作及其参数；**响应消息**是 Agent
对命令消息的回应，包含执行结果或错误信息；**观测消息**
是在观测类命令执行期间持续发送的数据流，包含函数调用的详细信息。命令消息和响应消息是一一对应的，而观测消息是流式的，一个命令可能触发多条观测消息。

### 4.2 消息格式定义

命令消息的基本结构包含一个 `type` 字段标识命令类型，以及其他命令特定的参数字段。不同的命令有不同的参数集合，但都遵循统一的消息格式。

**命令消息示例**：

```json
{
    "type": "watch",
    "action": "start",
    "pattern": "mymodule.MyClass.method",
    "depth": 2,
    "condition": "params[0] > 100",
    "times": -1
}
```

响应消息也采用统一格式，包含 `status` 字段表示执行状态，以及 `data` 或 `error` 字段提供详细信息。成功响应包含执行结果，错误响应包含错误描述和可选的堆栈跟踪。

**响应消息示例**：

```json
{
    "status": "success",
    "watch_id": "watch_001",
    "message": "Started watching mymodule.MyClass.method"
}
```

**错误响应示例**：

```json
{
    "status": "error",
    "error": "Cannot find target: mymodule.NonExistent",
    "traceback": "..."
}
```

观测消息包含被观测函数调用的详细信息，用于诊断目的的数据展示。

**观测消息示例**：

```json
{
    "type": "observation",
    "watch_id": "watch_001",
    "data": {
        "timestamp": 1705586200.123,
        "func_name": "mymodule.MyClass.method",
        "args": [42, "hello"],
        "kwargs": {"key": "value"},
        "result": 84,
        "success": true,
        "duration_ms": 0.123,
        "thread_id": 12345
    }
}
```

### 4.3 流式通信机制

对于需要持续传输数据的观测类命令，Peeka 提供了流式通信机制。与请求-响应模式不同，流式通信建立持久的连接，Agent
在观测期间持续发送数据，直到客户端主动断开或观测结束。这种模式特别适合观测高频率的函数调用，能够提供近实时的数据反馈。

流式通信的实现涉及客户端和服务器两端的协作。在客户端，`StreamingAgentClient` 类提供了 `watch()`
方法，返回一个生成器对象，调用者可以迭代获取观测数据。在内部，这个方法首先发送启动命令，然后在循环中持续读取消息，将观测消息中的数据项逐个产出。生成器的惰性求值特性使得客户端可以在收到第一条数据后就开始处理，而不需要等待观测结束。

```python
class StreamingAgentClient(AgentClient):
    """支持流式传输的客户端"""

    def watch(self, pattern: str, **options) -> Generator[dict, None, None]:
        """
        发起观测，返回生成器（惰性求值）
        
        Usage:
            for obs in client.watch("mymodule.MyClass.method", depth=2):
                print(obs)
        
        Yields:
            dict: 观测数据
        """
        command = {
            'type': 'watch',
            'action': 'start',
            'pattern': pattern,
            **options
        }

        # 发送开始命令
        response = self.send_command(command)
        if response['status'] != 'success':
            raise RuntimeError(response.get('error', 'Unknown error'))

        watch_id = response['watch_id']

        try:
            # 进入流式监听模式
            while True:
                msg = self._recv_message()
                if msg is None:
                    break

                msg_type = msg.get('type')

                if msg_type == 'observation':
                    yield msg['data']
                elif msg_type == 'stream_end':
                    break
                elif msg_type == 'error':
                    raise RuntimeError(msg['error'])

        finally:
            # 发送停止命令
            try:
                self.send_command({
                    'type': 'watch',
                    'action': 'stop',
                    'watch_id': watch_id
                })
            except Exception:
                pass
```

在 Agent 端，流式通信由 `_send_observation()` 方法支持，它将观测数据封装成观测消息格式，通过 Agent
的通信机制发送给客户端。这个方法在装饰器注入器的包装函数中被调用，每次函数调用发生时就会触发一次数据传输。

流式通信的一个关键设计考虑是资源管理。为了避免无限期的连接占用系统资源，流式观测支持通过 `--times`
参数限制观测次数，当达到指定的观测次数后，Agent 会自动发送流结束消息并停止观测。此外，Agent
还实现了连接超时机制，如果客户端在一定时间内没有读取数据，连接会被自动关闭。

## 5. 数据流设计

### 5.1 命令数据流

命令数据流描述了从用户输入命令到获得执行结果的完整过程，涉及 CLI 工具、Unix Domain Socket 和目标进程内的 Agent
三个执行环境。这个流程的设计需要处理序列化、网络传输、反序列化、执行和结果回传等多个环节。

**命令发起阶段**发生在 CLI 工具中，用户通过命令行参数指定要执行的诊断操作。CLI 解析器（如
argparse）负责解析用户输入，将其转换为结构化的参数对象。这些参数被组织成命令消息的格式，包括命令类型和必要的参数字段。对于复杂的诊断命令，参数可能包括模式字符串、过滤条件、输出格式等。

**消息发送阶段**将命令消息转换为字节流并通过网络套接字发送。发送过程首先使用 JSON 序列化将命令对象转换为字符串，然后计算字节长度并添加长度前缀，最后调用套接字的
`sendall()` 方法确保数据完整发送。`AgentClient` 类封装了这个过程，提供了简洁的 `send_command()` 接口。

**命令执行阶段**发生在目标进程内部的 Agent 中。Agent 的服务器套接字持续监听连接请求，收到命令后读取完整的消息内容，去除长度前缀并进行
JSON 反序列化。`_execute_command()` 方法根据命令类型查找对应的处理器并调用其 `execute()`
方法。执行过程中，处理器可能需要与装饰器注入器或观测管理器交互，执行诊断操作并收集结果。

**结果回传阶段**将执行结果发送回客户端。对于普通命令，执行结果直接封装在响应消息中发送；对于观测类命令，响应消息仅包含观测的元信息（如
watch_id），实际的观测数据通过流式机制单独发送。

### 5.2 观测数据流

观测数据流是 Peeka 实现实时诊断的关键，它描述了从目标函数被调用到观测数据被客户端接收的完整路径。这个数据流需要处理高频率的数据生成、临时缓冲、网络传输和实时展示等多个环节。

**数据生成**
发生在装饰器注入器的包装函数中。每次被观测的函数被调用时，包装函数会执行以下操作：首先捕获当前时间戳作为观测时间戳；然后获取函数的输入参数并进行格式化处理；接着调用原始函数获取执行结果或捕获异常；最后计算执行耗时。所有这些信息被组装成一个观测数据字典。

**数据传输阶段**
将观测数据从目标进程传递到客户端。由于装饰器注入器和观测管理器都在同一个进程内，这一步主要是进程内的函数调用开销。观测管理器接收数据后更新统计信息并添加到缓冲区，然后通过回调机制通知订阅者。对于流式观测，订阅者就是建立连接的客户端，数据被封装成观测消息格式通过网络发送。

**数据展示阶段**发生在客户端，CLI 工具接收观测数据并输出到控制台。默认情况下，观测数据以 JSON
格式输出，每条数据一行，便于通过管道传递给其他工具处理。客户端还可以实现更复杂的展示逻辑，如实时更新的表格、统计图表等。

### 5.3 状态管理流

状态管理流涉及观测生命周期的控制，包括观测的启动、状态查询和停止操作。这些操作确保诊断资源被正确管理，避免资源泄漏和不必要的性能开销。

**观测启动流程**从客户端发送带有 `action: start` 的命令开始。Agent 收到命令后，首先验证参数的有效性，然后调用装饰器注入器的
`inject()` 方法执行实际的函数替换，调用观测管理器的 `start_watch()` 方法注册新的观测，最后返回包含 watch_id 的成功响应。这个
watch_id 是后续控制操作的句柄。

**状态查询流程**允许客户端获取当前观测的运行时状态。Agent
的观测管理器维护了完整的统计信息，包括观测开始时间、已捕获的调用次数、错误次数等。查询命令返回这些统计信息，帮助用户了解观测的进展。

**观测停止流程**负责清理诊断操作所占用的资源。当用户主动停止观测或达到观测次数限制时，停止流程会被触发。Agent 首先调用装饰器注入器的
`uninject()` 方法恢复原始函数，然后调用观测管理器的 `stop_watch()`
方法生成最终的统计报告，最后清理相关的状态记录。这个过程确保了目标进程在诊断结束后恢复到正常状态，不会遗留任何诊断相关的代码修改。

## 6. 安全考虑

### 6.1 进程附加权限

进程附加是 Peeka 工具工作的基础，但也是潜在的安全风险点。在类 Unix 系统上，附加到另一个进程通常需要适当的系统权限。Linux
系统要求执行附加操作的进程具有 `CAP_SYS_PTRACE` 能力或有效的用户 ID 匹配；macOS 系统要求显式的用户授权或 root 权限；Windows
系统要求 `SeDebugPrivilege` 权限。这些权限要求确保了只有授权的用户才能诊断其他进程的内部行为。

在容器化环境中，权限控制更为复杂。Docker 容器默认禁用 `ptrace` 能力，需要在启动时显式添加 `--cap-add=SYS_PTRACE`
参数。对于生产环境，建议在受信任的网络环境中使用诊断功能，并记录所有诊断操作的审计日志。

### 6.2 代码注入安全

PEP 768 协议的设计考虑了代码注入的安全性，它要求通过文件系统路径传递要执行的代码，而不是直接在网络上传输代码内容。这种设计避免了远程代码执行的风险，因为攻击者需要能够访问目标文件系统的文件才能执行任意代码。同时，Agent
代码在目标进程中以目标进程的权限执行，遵循目标进程的沙箱限制。

为了防止恶意代码的执行，建议采取以下措施：确保 Agent 脚本文件的权限设置正确，仅允许授权用户读写；使用临时文件时设置合适的访问权限，并在使用后立即删除；在生产环境中部署时，对
Agent 代码进行代码审查，确保没有安全漏洞。

### 6.3 数据传输安全

Unix Domain Socket
提供了一定程度的进程间隔离，因为只有同一台机器上的进程能够访问这些套接字。然而，具有本地访问权限的攻击者仍可能截获传输的数据。对于处理敏感数据的场景，建议在应用层实现数据加密，或者使用文件权限严格限制套接字的访问。

套接字文件的位置选择也很重要。默认情况下，Peeka 将套接字文件创建在 `/tmp`
目录下，这个目录通常对所有用户可读。生产环境中可以考虑使用更私密的目录，或者在启动诊断前创建专门的目录并设置严格的权限。

### 6.4 资源限制

诊断操作可能消耗目标进程的系统资源，如 CPU 时间、内存和文件描述符。为了防止诊断操作影响目标进程的正常运行，Peeka
实现了多层次的资源限制机制。在观测频率方面，通过 `times`
参数限制总的观测次数，避免无限期的数据收集。在数据缓冲方面，使用固定大小的缓冲区防止内存无限增长。在连接管理方面，实现超时机制自动关闭空闲的诊断连接。

这些限制机制在保证诊断功能可用性的同时，确保了目标进程的稳定运行。实际部署时，可以根据目标系统的资源和业务需求调整这些限制参数。

## 7. 错误处理机制

### 7.1 异常分类与处理

Peeka Agent 的错误处理机制将异常分为几类，针对不同类型的异常采取不同的处理策略。**输入验证异常**
在命令参数不合法时抛出，这类异常通常由参数校验逻辑检测到，返回格式化的错误信息帮助用户修正输入。**运行时异常**
在命令执行过程中抛出，如目标函数不存在、条件表达式语法错误等，这类异常被捕获后转换为错误响应消息，包含异常的描述信息。**系统异常
**涉及底层的系统调用失败，如套接字错误、内存访问错误等，这类异常记录详细日志以便问题排查。

每个组件都有完善的异常处理逻辑。Agent 核心的 `_handle_client()`
方法捕获命令处理过程中的所有异常，确保单个命令的错误不会影响其他命令的处理和服务器的继续运行。装饰器注入器的包装函数使用
try-finally 结构确保异常情况下仍能记录观测数据。观测管理器在回调执行时捕获并忽略订阅者的异常，防止一个订阅者的错误影响其他订阅者。

### 7.2 错误恢复策略

错误恢复策略确保系统在发生异常后能够继续正常运行，或者在无法恢复时优雅地终止。连接级别的错误由服务器自动处理，断开的连接会被清理，服务器继续监听新的连接。命令执行级别的错误通过错误响应告知客户端，不会影响后续命令的处理。

对于更严重的错误，如资源耗尽，Agent 会尝试进行清理并主动退出。例如，如果数据缓冲区达到上限，Agent
会记录警告日志并继续运行，但可能会丢失最旧的观测数据。如果套接字创建失败，Agent 无法正常接收命令，会记录错误并阻止后续的诊断操作。

### 7.3 资源清理

资源清理是错误处理的重要组成部分，确保即使在异常情况下也不会留下资源泄漏。Agent 使用上下文管理器和 try-finally
结构来确保资源的正确释放。装饰器注入器在停止观测时恢复原始函数引用，不会遗留代码修改。观测管理器的缓冲区使用固定大小策略，自动管理内存使用。连接处理线程在退出时关闭套接字连接。

对于更彻底的清理，Agent 提供了 `cleanup()` 方法用于清理所有分配的临时资源，包括套接字文件、临时脚本文件、就绪标记文件等。这个方法在
Agent 正常退出或检测到严重错误时被调用。

## 8. 性能优化

### 8.1 数据格式化优化

观测数据的格式化是性能敏感的环节，特别是在高频率的函数调用场景下。Peeka
采用惰性格式化策略，即只有在数据需要被输出时才进行完整的格式化处理，平时只保留原始数据的引用。这种策略避免了不必要的数据转换开销。

格式化深度的控制也很重要。对于复杂的嵌套数据结构，默认只格式化到两层深度，避免展开过深的对象图。对于需要深入查看的场景，用户可以指定更大的深度参数，这种按需展开的设计平衡了信息完整性和性能开销。

### 8.2 内存使用优化

内存使用优化主要关注观测数据缓冲区和字符串 interning 两个方面。缓冲区使用固定大小的双端队列，自动淘汰最旧的数据，防止内存无限增长。对于高频率的观测场景，这个限制确保了内存使用的可预测性。

字符串 interning 是 Python 的内置优化机制，重复的字符串会共享同一个内存实例。Peeka
在生成观测数据时尽可能复用已有的字符串对象，减少内存分配压力。对于频繁出现的函数名、参数名等，使用 `sys.intern()` 进行
interning 处理。

### 8.3 传输效率优化

传输效率优化的核心是最小化传输的数据量。观测数据在发送前进行紧凑的 JSON 序列化，去除不必要的空白字符。使用
`separators=(',', ':')` 参数可以进一步减少输出大小。对于高频率的数据传输，可以考虑使用 MessagePack 或 Protocol Buffers
等二进制序列化格式，牺牲一定的可读性换取更高的传输效率。

批量传输是一种更进一步的优化策略。与其每收到一条观测数据就立即发送，可以积累一定数量的数据后批量发送，减少网络调用的次数。这种策略在高频率场景下可以显著提高传输效率，但会增加一定的延迟。

## 9. 扩展性设计

### 9.1 命令扩展机制

Peeka 的命令扩展机制遵循开闭原则，允许在不修改现有代码的情况下添加新的诊断命令。每个命令处理器都继承自 `BaseCommand`
抽象类，实现 `execute()` 方法定义具体的命令逻辑。新命令只需在 Agent 的 `_register_handlers()` 方法中注册到命令字典，即可被客户端调用。

命令注册采用自动发现机制，通过导入模块的方式加载所有已实现的命令处理器。这种设计使得添加新命令只需创建新的模块文件，不需要修改现有的注册逻辑。命令处理器之间相互独立，共享
Agent 核心提供的功能组件。

```python
class BaseCommand(ABC):
    """Base class for all diagnostic commands"""

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the command
        
        Args:
            params: Command parameters
            
        Returns:
            Dict containing execution results
        """
        pass

    def validate_params(self, params: Dict[str, Any], required: list) -> None:
        """
        Validate required parameters
        
        Args:
            params: Parameters to validate
            required: List of required parameter names
            
        Raises:
            ValueError: If required parameters are missing
        """
        missing = [p for p in required if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")
```

### 9.2 观测扩展机制

观测功能的扩展主要体现在观测策略和输出格式两个方面。对于观测策略，可以在装饰器注入器的基础上实现不同的观测方法，如基于
`sys.settrace()` 的全栈追踪、基于字节码插桩的低开销追踪等。这些不同的观测策略可以统一通过观测管理器提供的接口进行访问。

输出格式的扩展通过格式化器模式实现。默认的 JSON 格式化器输出结构化的数据，便于程序处理；可以添加其他格式化器如表格格式化器、简洁格式化器等，满足不同的展示需求。CLI
工具根据用户指定的格式参数选择相应的格式化器。

### 9.3 平台扩展机制

虽然 Peeka 默认仅支持 Linux 平台，但架构设计预留了跨平台扩展的能力。平台相关的代码被封装在 `platform`
模块中，通过抽象接口定义平台无关的操作。具体平台的实现（如 `LinuxPlatform`、`MacOSPlatform`）继承抽象类实现平台特定的行为。

当前版本的 Peeka 使用 `sys.remote_exec()` 进行进程附加，这个函数封装了平台差异，对上层应用提供统一的接口。如果需要支持更底层的协议或添加平台特定的功能，可以在平台模块中添加相应的实现。

## 10. 使用示例

### 10.1 基本观测流程

以下是一个完整的观测流程示例，演示如何使用 Peeka 诊断目标进程中的函数调用。首先启动一个演示应用作为诊断目标：

```bash
# 启动演示应用
$ python examples/demo.py --mode loop
╔════════════════════════════════════════════════════════════╗
║                  Peeka Demo Application                    ║
╚════════════════════════════════════════════════════════════╝
当前进程 PID: 12345
Running continuous loop. Press Ctrl+C to stop.
```

然后在另一个终端中附加到该进程并开始观测：

```bash
# 附加到进程
$ peeka attach 12345
[Peeka] Attaching to process 12345...
[Peeka] Successfully attached!
[Peeka] Socket path: /tmp/peeka_abc123.sock
[Peeka] You can now send commands to the target process
```

开始观测特定方法：

```bash
# 观测 Calculator.add 方法
$ peeka watch 12345 "demo.Calculator.add" --times 5
{"watch_id":"watch_001","timestamp":1705586200.123,"func_name":"demo.Calculator.add","args":[1,2],"kwargs":{},"result":3,"success":true,"duration_ms":0.123,"thread_id":12345}
{"watch_id":"watch_001","timestamp":1705586200.456,"func_name":"demo.Calculator.add","args":[3,4],"kwargs":{},"result":7,"success":true,"duration_ms":0.087,"thread_id":12345}
{"watch_id":"watch_001","timestamp":1705586200.789,"func_name":"demo.Calculator.add","args":[5,6],"kwargs":{},"result":11,"success":true,"duration_ms":0.098,"thread_id":12345}
{"watch_id":"watch_001","timestamp":1705586201.012,"func_name":"demo.Calculator.add","args":[7,8],"kwargs":{},"result":15,"success":true,"duration_ms":0.091,"thread_id":12345}
{"watch_id":"watch_001","timestamp":1705586201.345,"func_name":"demo.Calculator.add","args":[9,10],"kwargs":{},"result":19,"success":true,"duration_ms":0.095,"thread_id":12345}
```

### 10.2 条件过滤示例

条件过滤允许只观测满足特定条件的函数调用，减少无关数据的干扰：

```bash
# 只观测第一个参数大于 100 的调用
$ peeka watch 12345 "demo.Calculator.multiply" --condition "params[0] > 100"
{"watch_id":"watch_002","timestamp":1705586200.123,"func_name":"demo.Calculator.multiply","args":[101,2],"kwargs":{},"result":202,"success":true,"duration_ms":0.156,"thread_id":12345}
{"watch_id":"watch_002","timestamp":1705586200.456,"func_name":"demo.Calculator.multiply","args":[200,3],"kwargs":{},"result":600,"success":true,"duration_ms":0.142,"thread_id":12345}
```

### 10.3 数据处理示例

JSON 格式的输出便于与其他工具结合使用：

```bash
# 使用 jq 过滤结果
$ peeka watch 12345 "demo.Calculator.add" --times 100 | jq '.result'
3
7
11
15
...

# 统计调用次数
$ peeka watch 12345 "demo.Calculator.add" | wc -l

# 保存到文件便于后续分析
$ peeka watch 12345 "demo.Calculator.add" > observations.jsonl

# 筛选耗时超过 1ms 的调用
$ peeka watch 12345 "demo.Calculator.add" | jq 'select(.duration_ms > 1)'
```

### 10.4 与其他工具集成

Peeka 可以与各种 Python 开发工具集成，提供更强大的诊断能力：

```python
# 与 pandas 结合进行数据分析
import pandas as pd
import subprocess
import json

# 运行观测并解析结果
result = subprocess.run(
    ["peeka", "watch", "12345", "mymodule.Class.method", "--times", "1000"],
    capture_output=True,
    text=True
)

# 转换为 DataFrame
observations = [json.loads(line) for line in result.stdout.strip().split('\n')]
df = pd.DataFrame(observations)

# 分析执行时间分布
print(df['duration_ms'].describe())

# 分析成功率
success_rate = df['success'].mean()
print(f"Success rate: {success_rate:.2%}")
```

## 附录

### A. 环境变量

| 变量名               | 说明        | 默认值   |
|-------------------|-----------|-------|
| PEEKA_SOCKET_DIR  | 套接字文件目录   | /tmp  |
| PEEKA_TIMEOUT     | 命令超时时间（秒） | 30    |
| PEEKA_BUFFER_SIZE | 观测数据缓冲大小  | 10000 |

### B. 命令参考

| 命令     | 说明      | 示例                                |
|--------|---------|-----------------------------------|
| attach | 附加到目标进程 | `peeka attach 12345`              |
| watch  | 观测函数调用  | `peeka watch 12345 "module.func"` |

**watch 命令参数**：

| 参数          | 说明             | 默认值 |
|-------------|----------------|-----|
| --depth, -x | 输出深度           | 2   |
| --times, -n | 观测次数 (-1 表示无限) | -1  |
| --condition | 条件表达式          | 无   |

### C. 故障排除

**问题：附加失败，权限被拒绝**

确保运行 Peeka 的用户具有附加到目标进程的权限。在 Linux 上可能需要 root 权限或调整 ptrace 范围：

```bash
# 临时放宽 ptrace 限制
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

**问题：观测不到数据**

检查目标函数的名称是否正确，使用完整的限定名称。如果目标函数是动态创建的，可能需要使用不同的观测策略。

**问题：观测后目标进程行为异常**

这通常是由于装饰器注入没有正确恢复导致的。使用 `peeka watch --action stop` 命令停止观测，如果问题持续，可能需要重启目标进程。

### D. 版本历史

| 版本    | 日期      | 说明                  |
|-------|---------|---------------------|
| 0.1.0 | 2025-01 | 初始版本，支持基本的 watch 功能 |

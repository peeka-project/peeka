# Peeka 场景案例教程

## 前言

Peeka 是一个基于 [PEP 768](https://peps.python.org/pep-0768/) 远程调试的 Python 运行时诊断工具，支持 Python 3.8-3.14+。本文档通过 8 个真实场景案例，展示如何使用 peeka-cli 排查 Python 应用中的常见问题。

### 本文档定位

- **目标读者**：Python 开发者、运维工程师、SRE
- **学习目标**：掌握 peeka-cli 命令的实战应用
- **前置知识**：Python 基础、命令行操作

### 如何使用本文档

1. 按顺序阅读场景，每个场景独立完整
2. 每个场景包含：问题描述 → 启动示例 → 诊断步骤 → 根因分析 → 修复建议
3. 所有示例代码位于 `examples/` 目录，可直接运行
4. 所有命令输出为 JSONL 格式，可用 `jq` 过滤
5. 文中的输出示例经过精简（省略了路径、ID 等字段），实际运行的完整输出和 TUI 截图见 [scenario-demos.md](scenario-demos.md)

## 前置准备

### 安装 Peeka

```bash
# 安装 peeka（Python 3.8+）
pip install peeka
```

### Python < 3.14 额外要求

Python 3.14+ 原生支持 PEP 768，无需额外配置。Python 3.8-3.13 需要 GDB + ptrace 支持：

```bash
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# 检查 ptrace 权限
cat /proc/sys/kernel/yama/ptrace_scope  # 应为 0 或 1
```

### 启动示例脚本

每个场景对应一个 Python 脚本，启动方式：

```bash
python examples/scenario_1_order_bug.py &
# 输出: PID: 12345

# 记录 PID，用于 attach
```

### Attach 到进程

```bash
peeka-cli attach 12345
```

所有后续命令依赖 attach 状态，诊断完成后使用 `peeka-cli detach` 分离。

---

## 场景 1：电商订单金额计算错误

### 问题描述

电商系统中，客户反馈订单金额异常。正常情况下，20% 折扣的订单应该打 8 折（乘以 0.8），但实际金额却变成了原价的 20 倍。

**症状**：
- 大部分订单金额正常
- 每 5 个订单中有 1 个金额异常（折扣订单）
- 折扣订单金额 = 原价 × 折扣值（错误的计算方式）

### 启动示例脚本

```bash
python examples/scenario_1_order_bug.py &
# 输出：PID: 12345
```

### 诊断步骤

#### 步骤 1：Attach 到进程

```bash
peeka-cli attach 12345
```

输出：
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_xxx.sock"}}
```

#### 步骤 2：观察订单计算函数

```bash
peeka-cli watch '__main__.OrderProcessor.calculate_total' -n 10
```

输出示例：
```json
{"type":"event","event":"watch_started","data":{"watch_id":"watch_001","pattern":"__main__.OrderProcessor.calculate_total"}}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.123,"func_name":"__main__.OrderProcessor.calculate_total","args":[{"order_id":1,"items":[[100,2],[50,1]],"discount":0}],"kwargs":{},"result":250.0,"success":true,"duration_ms":0.05,"count":1}
{"type":"observation","watch_id":"watch_001","timestamp":1705586202.456,"func_name":"__main__.OrderProcessor.calculate_total","args":[{"order_id":5,"items":[[100,2],[50,1]],"discount":20}],"kwargs":{},"result":5000.0,"success":true,"duration_ms":0.06,"count":5}
```

**分析**：
- 第 1 个订单：无折扣，subtotal=250，total=250 ✓
- 第 5 个订单：20% 折扣，subtotal=250，**total=5000** ✗（异常！应该是 200）

#### 步骤 3：查看调用栈确认调用路径

```bash
peeka-cli stack '__main__.OrderProcessor.calculate_total' -n 2
```

输出示例：
```json
{"type":"observation","data":{"pattern":"__main__.OrderProcessor.calculate_total","stack":[{"file":"examples/scenario_1_order_bug.py","line":135,"function":"process_order","code":"total = self.processor.calculate_total(order)"},{"file":"examples/scenario_1_order_bug.py","line":150,"function":"main","code":"app.process_order(order)"}],"count":1}}
```

### 根因分析

通过观察发现：
- 当 `discount=20` 时，`total=5000`（原价 250 × 20）
- 预期应该是 `total=200`（原价 250 × 0.8）

**Bug 位置**：`OrderProcessor.calculate_total()` 方法

**错误代码**：
```python
# 错误：直接乘以折扣值（20）
total = subtotal * order.discount  # 250 * 20 = 5000
```

**正确代码**：
```python
# 正确：折扣百分比转换为乘数
total = subtotal * (1 - order.discount / 100.0)  # 250 * (1 - 0.2) = 200
```

### 修复建议

修改 `examples/scenario_1_order_bug.py` 第 69 行：

```python
def calculate_total(self, order):
    subtotal = order.get_subtotal()
    if order.discount > 0:
        # 修复：正确计算折扣
        total = subtotal * (1 - order.discount / 100.0)
    else:
        total = subtotal
    return total
```

### 清理

```bash
peeka-cli reset
peeka-cli detach
kill 12345
```

---

## 场景 2：API 偶发慢请求

### 问题描述

API 服务大部分时间响应正常（~5ms），但偶尔出现超过 1 秒的慢请求。用户投诉特定搜索功能响应慢。

**症状**：
- 90% 的请求响应时间 < 20ms
- 10% 的请求响应时间 > 1000ms
- 慢请求集中在产品搜索接口
- 搜索关键词越长，越容易触发慢请求

### 启动示例脚本

```bash
python examples/scenario_2_slow_api.py &
# 输出：PID: 23456
```

### 诊断步骤

#### 步骤 1：Attach 并监控性能

```bash
peeka-cli attach 23456
peeka-cli monitor '__main__.DatabaseSimulator.search_products' --interval 5 -c 2
```

`monitor` 需要具体到函数的 pattern（只写类名不会统计任何调用）。每个周期输出一行统计，`rt_*` 单位为毫秒。

输出示例：
```json
{"type":"event","event":"monitor_started","data":{"monitor_id":"monitor_66328cb6","pattern":"__main__.DatabaseSimulator.search_products"}}
{"type":"observation","cycle":1,"total":6,"success":6,"fail":0,"fail_rate":0.0,"rt_avg":168.1,"rt_min":0.02,"rt_max":1008.5}
{"type":"observation","cycle":2,"total":13,"success":13,"fail":0,"fail_rate":0.0,"rt_avg":155.2,"rt_min":0.02,"rt_max":1009.3}
```

**分析**：大部分调用不到 1ms，但 `rt_max` 每个周期都在 1000ms 左右，说明存在偶发慢调用

#### 步骤 2：捕获慢请求

使用 `--condition` 过滤器只观察耗时超过 200ms 的调用：

```bash
peeka-cli watch '__main__.DatabaseSimulator.search_products' --condition "cost > 200" -n 3
```

输出示例：
```json
{"type":"event","event":"watch_started","data":{"watch_id":"watch_e1c2a3b4","pattern":"__main__.DatabaseSimulator.search_products"}}
{"type":"observation","func_name":"__main__.DatabaseSimulator.search_products","params":["high performance laptop computer"],"returnObj":[],"success":true,"cost":1008.7,"thread_name":"MainThread"}
```

**分析**：慢请求的入参都是长查询字符串（> 10 字符），短查询从不出现在结果里

#### 步骤 3：追踪调用树

```bash
peeka-cli trace '__main__.ApiService.handle_product_search' -n 1 --condition "cost > 200"
```

`trace` 记录被追踪函数的直接子调用（默认跳过内置函数）。

输出示例：
```json
{"type":"observation","func_name":"__main__.ApiService.handle_product_search","total_duration_ms":1008.7,"self_time_ms":0.09,"call_tree":[{"function":"__main__.DatabaseSimulator.search_products","lineno":60,"count":1,"total_ms":1008.6}]}
```

**分析**：请求的 1008ms 几乎全部花在 `search_products()` 里，问题在这个函数内部

### 根因分析

**Bug 位置**：`DatabaseSimulator.search_products()` 方法

**问题代码**（第 60-92 行）：
```python
def search_products(self, query_str):
    if len(query_str) > 10:
        # 慢路径：逐行模拟 I/O，外加冗余的内层比较循环
        results = []
        for product in self.product_catalog:
            time.sleep(0.01)  # 每个商品一次 10ms 的 I/O
            matched = False
            for _ in range(100):
                matched = query_str.lower() in product["name"].lower()
            if matched:
                results.append(product)
        return results
    else:
        # 快速路径：列表推导
        return [p for p in self.product_catalog if query_str.lower() in p["name"].lower()]
```

**触发条件**：
- 请求序号是 7 的倍数的商品搜索会使用长查询字符串（32 字符）
- 长查询走慢路径分支
- 100 个商品 × 每个 10ms 的模拟 I/O ≈ 1 秒

### 修复建议

统一使用高效的列表推导，移除嵌套循环：

```python
def search_products(self, query_str):
    terms = query_str.lower().split()
    return [
        p for p in self.product_catalog
        if any(term in p["name"].lower() for term in terms)
    ]
```

### 清理

```bash
peeka-cli reset
peeka-cli detach
kill 23456
```

---

## 场景 3：CPU 占用过高

### 问题描述

数据处理服务 CPU 使用率持续在 20-30%，远高于预期的 5%。经过排查发现是数据转换函数存在重复计算。

**症状**：
- CPU 使用率持续偏高
- 批量处理速度慢于预期
- 单个函数调用耗时正常，但频繁调用累积效应明显

### 启动示例脚本

```bash
python examples/scenario_3_high_cpu.py &
# 输出：PID: 34567
```

### 诊断步骤

#### 步骤 1：Attach 并采样热点函数

```bash
peeka-cli attach 34567
peeka-cli top --cycles 3
```

`top` 对整个进程做栈采样（默认每 10ms 一次，自动排除 peeka 自己的线程），每个周期输出一次按 `own_pct` 排序的函数列表。

输出示例（每个周期一行，这里只保留前几个函数）：
```json
{"type":"event","event":"top_started","data":{"top_id":"top_f456c21b","interval":0.01,"filter_peeka":true}}
{"type":"observation","total_samples":230,"functions":[{"name":"main","filename":"examples/scenario_3_high_cpu.py","line":165,"own_pct":55.2,"total_pct":55.2},{"name":"transform_data","filename":"examples/scenario_3_high_cpu.py","line":80,"own_pct":10.9,"total_pct":10.9},{"name":"process_batch","filename":"examples/scenario_3_high_cpu.py","line":107,"own_pct":0.0,"total_pct":20.4}]}
```

**分析**：除了主循环本身，`transform_data()` 是最大的业务热点，`process_batch()` 的 total 时间主要由它贡献

#### 步骤 2：追踪调用树查看时间分布

```bash
peeka-cli trace '__main__.DataProcessor.process_batch' -n 3
```

输出示例（树形格式）：
```
`---[165.3ms] __main__.DataProcessor.process_batch()
    +---[8.2ms] __main__.DataProcessor.generate_batch()
    `---[155.8ms] __main__.DataProcessor.transform_data()
```

**分析**：`transform_data()` 占用 94% 的批处理时间

#### 步骤 3：观察函数执行细节

```bash
peeka-cli watch '__main__.DataProcessor.transform_data' -n 5
```

输出示例：
```json
{"type":"observation","watch_id":"watch_003","timestamp":1705586400.1,"func_name":"__main__.DataProcessor.transform_data","args":[[{"id":1,"value":500.5,"category":"A"},{"id":2,"value":230.8,"category":"B"}]],"kwargs":{},"result":[{"id":1,"value":500.5,"category":"A"},{"id":2,"value":230.8,"category":"B"}],"success":true,"duration_ms":158.3,"count":1}
{"type":"observation","watch_id":"watch_003","timestamp":1705586400.3,"func_name":"__main__.DataProcessor.transform_data","args":[[{"id":1,"value":750.2,"category":"C"}]],"kwargs":{},"result":[{"id":1,"value":750.2,"category":"C"}],"success":true,"duration_ms":162.1,"count":2}
```

**分析**：每次调用耗时 ~160ms，批量大小不大（只有几百条记录），说明算法效率低

### 根因分析

**Bug 位置**：`DataProcessor.transform_data()` 方法

**问题代码**（第 55-98 行）：
```python
def transform_data(self, data):
    # BUG 1: 第一次排序
    sorted_data = sorted(data, key=lambda x: x["value"])
    
    # BUG 2: 迭代已排序数据进行验证（没有缓存排序结果）
    validated = []
    for record in sorted_data:
        if record["value"] > 0:
            validated.append({...})
    
    # BUG 3: 又一次排序（应该复用前面的排序结果）
    refined = sorted(validated, key=lambda x: x["value"], reverse=True)
    
    return refined[:100]
```

**性能问题**：
- 对同一数据集排序 **3 次**（2 次正序，1 次倒序）
- 没有缓存中间结果
- 在循环调用场景下，O(n log n) × 3 累积成显著开销

### 修复建议

缓存排序结果，避免重复排序：

```python
def transform_data(self, data):
    # 只排序一次
    sorted_data = sorted(data, key=lambda x: x["value"], reverse=True)
    
    # 直接在排序结果上验证
    validated = [
        {"id": r["id"], "value": r["value"], "category": r["category"]}
        for r in sorted_data
        if r["value"] > 0
    ]
    
    return validated[:100]
```

### 清理

```bash
peeka-cli reset
peeka-cli detach
kill 34567
```

---

## 场景 4：内存持续增长

### 问题描述

缓存系统运行后内存持续增长，未见下降趋势。怀疑存在内存泄漏。

**症状**：
- 内存使用量线性增长（约 100KB/秒）
- 缓存大小持续增加，从不清理
- 没有 OOM，但内存占用不合理

### 启动示例脚本

```bash
python examples/scenario_4_memory_leak.py &
# 输出：PID: 45678
```

### 诊断步骤

#### 步骤 1：Attach 并启动内存追踪

```bash
peeka-cli attach 45678

# 关键步骤：启动 tracemalloc
peeka-cli memory --action start
```

输出：
```json
{"type":"success","command":"memory","data":{"action":"start","message":"Memory tracking started"}}
```

**注意**：必须先执行 `memory --action start`，否则后续的 `top`/`snapshot`/`diff` 命令无法工作。

#### 步骤 2：查看内存分配热点

```bash
peeka-cli memory --action top --limit 10
```

输出示例：
```json
{"type":"result","command":"memory","data":{"action":"top","top_allocations":[{"file":"examples/scenario_4_memory_leak.py","line":52,"size_kb":2450.5,"count":12500,"average_kb":0.196},{"file":"examples/scenario_4_memory_leak.py","line":105,"size_kb":850.3,"count":5000,"average_kb":0.170}]}}
```

**分析**：第 52 行（`CacheManager.add()` 方法）分配了 2.45MB 内存

#### 步骤 3：第一次内存快照

```bash
peeka-cli memory --action snapshot
```

输出：
```json
{"type":"success","command":"memory","data":{"action":"snapshot","snapshot_id":1,"total_mb":45.2,"traceback_count":156}}
```

#### 步骤 4：等待内存增长

```bash
# 等待 30 秒，让缓存继续增长
sleep 30
```

#### 步骤 5：第二次快照并对比

```bash
# 第二次快照
peeka-cli memory --action snapshot

# 对比两次快照的差异
peeka-cli memory --action diff
```

输出示例：
```json
{"type":"result","command":"memory","data":{"action":"diff","snapshot_1":1,"snapshot_2":2,"diff_mb":3.2,"top_increases":[{"file":"examples/scenario_4_memory_leak.py","line":52,"size_increase_kb":3100.5,"count_increase":15000},{"file":"examples/scenario_4_memory_leak.py","line":105,"size_increase_kb":450.2,"count_increase":2500}]}}
```

**分析**：第 52 行增长了 3.1MB，增加了 15000 次分配

#### 步骤 6：检查缓存对象状态

```bash
peeka-cli inspect --action instances --type '__main__.CacheManager' --limit 1 --depth 1
```

`cache_manager` 是 `main()` 的局部变量，无法用 `--target` 按路径访问，所以按类型列出存活实例。

输出示例：
```json
{"type":"result","command":"vmtool","data":{"action":"instances","class_name":"__main__.CacheManager","count":1,"instances":[{"__class__":"__main__.CacheManager","__attrs__":{"cache":"{'request_100': {'request_id': 100, 'timestamp': ..., 'data': 'xxxx...'}, ...}","hits":"0","misses":"4900"}}]}}
```

**分析**：`hits` 一直是 0、`misses` 持续增长，缓存只进不出

### 根因分析

**Bug 位置**：`CacheManager.add()` 方法

**问题代码**（第 40-52 行）：
```python
def add(self, key, value):
    # BUG：只添加，从不删除！
    self.cache[key] = value
    # 缺少：LRU 淘汰、TTL 过期、max_size 限制
```

**内存泄漏原因**：
- 每个请求都生成唯一的 cache key
- `add()` 方法只添加，从不检查缓存大小
- 没有任何淘汰机制（LRU/TTL/max_size）
- 缓存无限增长，最终导致 OOM

### 修复建议

添加 LRU 淘汰机制：

```python
from collections import OrderedDict

class CacheManager:
    def __init__(self, max_size=1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    def add(self, key, value):
        # 如果已存在，先移除（移到末尾）
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        
        # LRU 淘汰：超过 max_size 时删除最旧条目
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
```

### 清理

```bash
peeka-cli memory --action stop
peeka-cli reset
peeka-cli detach
kill 45678
```

---

## 场景 5：多线程死锁

### 问题描述

银行转账系统在高并发时偶尔出现死锁，两个 worker 线程互相等待对方持有的锁，导致转账业务停滞。

**症状**：
- 主线程正常响应
- Worker 线程卡住不动
- 日志显示转账请求开始，但没有完成记录
- 进程没有崩溃，CPU 使用率正常，但业务停滞

### 启动示例脚本

```bash
python examples/scenario_5_deadlock.py &
# 输出：PID: 56789
```

### 诊断步骤

#### 步骤 1：Attach 并查看线程列表

```bash
peeka-cli attach 56789
peeka-cli thread
```

输出示例：
```json
{"type":"result","command":"thread","data":{"threads":[{"id":1,"name":"MainThread","daemon":false,"state":"RUNNABLE","current_frame":{"file":"examples/scenario_5_deadlock.py","line":220,"function":"main"}},{"id":2,"name":"worker_1","daemon":true,"state":"WAITING","current_frame":{"file":"examples/scenario_5_deadlock.py","line":85,"function":"transfer"}},{"id":3,"name":"worker_2","daemon":true,"state":"WAITING","current_frame":{"file":"examples/scenario_5_deadlock.py","line":85,"function":"transfer"}}]}}
```

**分析**：
- MainThread: **RUNNABLE**（正常运行）
- worker_1: **WAITING**（等待锁）
- worker_2: **WAITING**（等待锁）

#### 步骤 2：查看卡住线程的调用栈

死锁的线程不会再进入 `transfer()`，`stack` 这类"等下一次调用"的命令抓不到它们，应直接读取线程当前的栈：

```bash
peeka-cli thread --tid <Worker 线程的 tid> --depth 8
```

输出示例：
```json
{"type":"result","command":"thread","data":{"action":"detail","thread":{"tid":140655304402624,"name":"Worker-B→A","state":"RUNNABLE","stack":[{"filename":"examples/scenario_5_deadlock.py","lineno":103,"funcname":"transfer","locals_keys":["self","from_account","to_account","amount"]},{"filename":"examples/scenario_5_deadlock.py","lineno":149,"funcname":"worker_b_to_a"},{"filename":"threading.py","lineno":1024,"funcname":"run"}]}}}
```

两个 Worker 线程都停在 `transfer()` 第 103 行（`with to_account.lock:`）。注意 `state` 显示为 RUNNABLE：Python 层面看不到线程是否阻塞在锁上，要靠"栈长时间不变"来判断。

**分析**：
- Worker-A→B: 持有 account_a.lock，等待 account_b.lock
- Worker-B→A: 持有 account_b.lock，等待 account_a.lock
- 形成**循环等待**，死锁！

### 根因分析

**Bug 位置**：`TransferService.transfer()` 方法

**问题代码**（第 75-100 行）：
```python
def transfer(self, from_account, to_account, amount):
    # BUG：按调用顺序获取锁
    with from_account.lock:  # Thread A 锁定 account1
        time.sleep(random.uniform(0.01, 0.05))  # 增加死锁窗口
        
        with to_account.lock:  # Thread A 等待 account2（Thread B 持有）
            # 转账逻辑
            if from_account.debit(amount):
                to_account.credit(amount)
                self.transfers_completed += 1
                return True
    return False
```

**死锁场景**：
- Thread A: `transfer(account1, account2, 100)` → 锁定 account1，等待 account2
- Thread B: `transfer(account2, account1, 50)` → 锁定 account2，等待 account1
- **循环等待** → 死锁

### 修复建议

使用**全局锁定顺序**（按账户 ID 排序）避免循环等待：

```python
def transfer(self, from_account, to_account, amount):
    # 修复：按账户 ID 排序，确保全局锁定顺序一致
    accounts = sorted([from_account, to_account], key=lambda a: a.account_id)
    
    with accounts[0].lock:
        with accounts[1].lock:
            # 转账逻辑（需要判断转账方向）
            if from_account.debit(amount):
                to_account.credit(amount)
                with self.transfer_lock:
                    self.transfers_completed += 1
                return True
    return False
```

### 清理

```bash
peeka-cli reset
peeka-cli detach
kill 56789
```

---

## 场景 6：线上紧急诊断

### 问题描述

生产环境应用出现异常，但日志信息不足，需要紧急诊断。已知问题：
- 某个内部缓存在膨胀
- 重试计数器异常增长
- DEBUG 日志被关闭，看不到详细信息

**症状**：
- 应用运行缓慢
- 内存占用持续增长
- 日志输出不完整（缺少 DEBUG 信息）
- 不知道有哪些类和方法可用

### 启动示例脚本

```bash
python examples/scenario_6_emergency_diag.py &
# 输出：PID: 67890
```

### 诊断步骤

#### 步骤 1：探索可用的类

```bash
peeka-cli attach 67890
peeka-cli sc '__main__.*Service'
```

输出示例：
```json
{"type":"result","command":"sc","data":{"classes":[{"name":"__main__.UserService"}],"count":1}}
```

**分析**：找到了 `UserService` 类

#### 步骤 2：探索类的方法

```bash
peeka-cli sm '__main__.UserService'
```

输出示例：
```json
{"type":"result","command":"sm","data":{"methods":[{"name":"get_user","signature":"(self, user_id)"}],"count":1}}
```

**分析**：`UserService` 只有一个公开方法 `get_user()`

#### 步骤 3：检查内部状态

```bash
peeka-cli inspect --action instances --type '__main__.UserService' --limit 1 --depth 1
```

输出示例：
```json
{"type":"result","command":"vmtool","data":{"action":"instances","class_name":"__main__.UserService","count":1,"instances":[{"__class__":"__main__.UserService","__attrs__":{"config":"<__main__.AppConfig object at 0x7feaf30b8c20>","logger":"<Logger __main__ (WARNING)>","users_fetched":"52"}}]}}
```

**分析**：
- `inspect` 和 `watch` 的对象输出都不显示 `_` 开头的私有属性，所以 `_cache`、`_retry_count` 本身看不到
- 但 `users_fetched` 每次缓存未命中都会加一，它持续增长说明缓存未命中一直在发生，`_cache` 也随之同步增长
- 结合源码可以确认 `_cache` 没有淘汰、`_retry_count` 从不重置

#### 步骤 4：调整日志级别

```bash
# 列出所有 logger
peeka-cli logger --action list
```

输出示例：
```json
{"type":"result","command":"logger","data":{"loggers":[{"name":"__main__","level":"WARNING","level_num":30,"handlers":0}],"count":1}}
```

```bash
# 将 __main__ logger 级别调整为 DEBUG
peeka-cli logger --action set --logger __main__ --level DEBUG
```

输出：
```json
{"type":"result","command":"logger","data":{"name":"__main__","old_level":"WARNING","new_level":"DEBUG","old_level_num":30,"new_level_num":10}}
```

#### 步骤 5：观察函数行为

```bash
peeka-cli watch '__main__.UserService.get_user' -n 5
```

输出示例（现在有 DEBUG 日志了）：
```json
{"type":"observation","watch_id":"watch_004","timestamp":1705586500.1,"func_name":"__main__.UserService.get_user","args":[123],"kwargs":{},"result":{"user_id":123,"name":"User 123","email":"user123@example.com"},"success":true,"duration_ms":2.5,"count":1}
```

同时终端日志输出（因为调高了日志级别）：
```
2024-01-18 10:15:00 - __main__ - DEBUG - Cache size: 8501 entries
2024-01-18 10:15:00 - __main__ - DEBUG - Retry count: 12501
```

### 根因分析

**Bug 1**：`UserService._cache` 无界增长
- 位置：`get_user()` 方法
- 每次调用都添加新条目，从不清理

**Bug 2**：`UserService._retry_count` 无限递增
- 位置：`get_user()` 方法
- 每次调用都递增，从不重置

**Bug 3**：日志级别配置不当
- 默认为 WARNING，隐藏了 DEBUG 信息
- 需要运行时调整才能看到详细日志

### 修复建议

1. **添加缓存淘汰**：
```python
def get_user(self, user_id):
    if user_id in self._cache:
        return self._cache[user_id]
    
    user = {"user_id": user_id, "name": f"User {user_id}", ...}
    
    # 修复：限制缓存大小
    if len(self._cache) > 1000:
        # 移除最旧的条目
        self._cache.pop(next(iter(self._cache)))
    
    self._cache[user_id] = user
    return user
```

2. **合理管理重试计数**：
```python
def get_user(self, user_id):
    max_retries = self.config.thresholds.get("max_retries", 3)
    
    for attempt in range(max_retries):  # 使用局部变量
        try:
            return self._fetch_user(user_id)
        except Exception:
            if attempt == max_retries - 1:
                raise
```

3. **调整默认日志级别**：
```python
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
```

### 清理

```bash
peeka-cli logger --action set --logger __main__ --level WARNING
peeka-cli reset
peeka-cli detach
kill 67890
```

---

## 场景 7："谁在调用我"

### 问题描述

数据库查询频率异常高，怀疑某个服务过度调用 `Database.execute_query()`。需要找出是哪个服务、调用频率多高。

**症状**：
- 数据库查询 QPS 比预期高 5 倍
- 多个服务共享同一个数据库连接
- 不知道是哪个服务贡献了大部分查询

### 启动示例脚本

```bash
python examples/scenario_7_who_calls_me.py &
# 输出：PID: 78901
```

### 诊断步骤

#### 步骤 1：捕获调用栈识别调用方

```bash
peeka-cli attach 78901
peeka-cli stack '__main__.Database.execute_query' -n 10
```

输出示例：
```json
{"type":"observation","data":{"pattern":"__main__.Database.execute_query","stack":[{"file":"examples/scenario_7_who_calls_me.py","line":95,"function":"get_user","code":"return self.db.execute_query(sql)"},{"file":"examples/scenario_7_who_calls_me.py","line":280,"function":"worker_users","code":"repo.get_user(user_id)"}],"caller":"UserRepository.get_user","count":1}}
{"type":"observation","data":{"pattern":"__main__.Database.execute_query","stack":[{"file":"examples/scenario_7_who_calls_me.py","line":135,"function":"get_order","code":"return self.db.execute_query(sql)"},{"file":"examples/scenario_7_who_calls_me.py","line":295,"function":"worker_orders","code":"repo.get_order(order_id)"}],"caller":"OrderRepository.get_order","count":2}}
{"type":"observation","data":{"pattern":"__main__.Database.execute_query","stack":[{"file":"examples/scenario_7_who_calls_me.py","line":185,"function":"generate_daily_report","code":"users = self.db.execute_query(sql_users)"},{"file":"examples/scenario_7_who_calls_me.py","line":310,"function":"worker_reports","code":"service.generate_daily_report()"}],"caller":"ReportService.generate_daily_report","count":3}}
{"type":"observation","data":{"pattern":"__main__.Database.execute_query","stack":[{"file":"examples/scenario_7_who_calls_me.py","line":188,"function":"generate_daily_report","code":"orders = self.db.execute_query(sql_orders)"},{"file":"examples/scenario_7_who_calls_me.py","line":310,"function":"worker_reports","code":"service.generate_daily_report()"}],"caller":"ReportService.generate_daily_report","count":4}}
```

**分析**：发现 3 个调用方：
- `UserRepository.get_user` (count=1)
- `OrderRepository.get_order` (count=2)
- `ReportService.generate_daily_report` (count=3, 4, ...) ← 高频！

#### 步骤 2：观察调用频率

```bash
peeka-cli watch '__main__.Database.execute_query' -n 20
```

输出示例（统计 20 次调用）：
```json
{"type":"observation","watch_id":"watch_005","timestamp":1705586600.1,"func_name":"__main__.Database.execute_query","args":["SELECT * FROM users WHERE id=123"],"kwargs":{},"result":{"query_count":1,"sql":"SELECT ...","rows":1},"success":true,"duration_ms":1.2,"count":1}
{"type":"observation","watch_id":"watch_005","timestamp":1705586600.3,"func_name":"__main__.Database.execute_query","args":["SELECT users FROM reports"],"kwargs":{},"result":{"query_count":2,"sql":"SELECT ...","rows":50},"success":true,"duration_ms":2.5,"count":2}
{"type":"observation","watch_id":"watch_005","timestamp":1705586600.4,"func_name":"__main__.Database.execute_query","args":["SELECT orders FROM reports"],"kwargs":{},"result":{"query_count":3,"sql":"SELECT ...","rows":100},"success":true,"duration_ms":3.1,"count":3}
...
```

统计发现：
- 20 次调用中，**15 次来自 ReportService**（75%）
- 3 次来自 UserRepository（15%）
- 2 次来自 OrderRepository（10%）

#### 步骤 3：追踪报表服务调用树

```bash
peeka-cli trace '__main__.ReportService.generate_daily_report' -n 2
```

输出示例（树形格式）：
```
`---[25.5ms] __main__.ReportService.generate_daily_report()
    +---[2.5ms] __main__.Database.execute_query("SELECT users FROM reports")
    +---[3.1ms] __main__.Database.execute_query("SELECT orders FROM reports")
    +---[2.8ms] __main__.Database.execute_query("SELECT products FROM reports")
    +---[4.2ms] __main__.Database.execute_query("SELECT stats FROM reports")
    `---[3.5ms] __main__.Database.execute_query("SELECT summary FROM reports")
```

**分析**：`generate_daily_report()` **每次调用执行 5 个查询**！

### 根因分析

**问题**：`ReportService.generate_daily_report()` 方法

**代码位置**（第 175-205 行）：
```python
def generate_daily_report(self):
    # 问题：每次生成报表执行 5 个独立查询
    users = self.db.execute_query("SELECT users FROM reports")
    orders = self.db.execute_query("SELECT orders FROM reports")
    products = self.db.execute_query("SELECT products FROM reports")
    stats = self.db.execute_query("SELECT stats FROM reports")
    summary = self.db.execute_query("SELECT summary FROM reports")
    
    # 聚合结果
    return {"users": len(users), "orders": len(orders), ...}
```

**调用频率**：
- ReportService 以 ~5 Hz 生成报表
- 每次报表 × 5 个查询 = **25 查询/秒**
- UserRepository: ~1 查询/秒
- OrderRepository: ~0.5 查询/秒
- **ReportService 贡献了 90% 的查询负载**

### 修复建议

合并多个查询为单个 JOIN 查询：

```python
def generate_daily_report(self):
    # 修复：使用一个 JOIN 查询代替 5 个查询
    sql = """
        SELECT 
            COUNT(DISTINCT u.id) as user_count,
            COUNT(DISTINCT o.id) as order_count,
            COUNT(DISTINCT p.id) as product_count,
            SUM(o.amount) as total_amount
        FROM reports r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN orders o ON r.order_id = o.id
        LEFT JOIN products p ON o.product_id = p.id
    """
    result = self.db.execute_query(sql)
    return result
```

优化后：
- 从 5 查询/报表 → 1 查询/报表
- 总 QPS 从 ~27 降至 ~7（减少 75%）

### 清理

```bash
peeka-cli reset
peeka-cli detach
kill 78901
```

---

## 场景 8: 检测 Monkey-Patched 目标进程

### 问题描述

你的应用使用 gevent 或 eventlet 等异步框架来提升并发性能。这些框架会在运行时替换标准库的 `socket`、`threading`、`time` 等模块（monkey-patching）。你想确认目标进程是否被 patch 了，以及 Peeka 的诊断基础设施是否能正常工作。

### 症状表现

- 应用使用 `gevent.monkey.patch_all()` 或 `eventlet.monkey_patch()`
- 不确定哪些模块被 patch 了
- 想验证 Peeka 的 agent 是否能在 patch 环境下正常运行

### 启动示例

```bash
# 启动 gevent-patched 示例
python examples/gevent_attach_target.py &
# 输出：PID: 12345
# Patched: socket=True, threading=True
```

### Attach 步骤

```bash
peeka-cli attach 12345
```

### 诊断步骤

#### 步骤 1: 查看 Patch 状态

```bash
peeka-cli patch-status
```

预期输出（JSONL）：
```json
{
  "type": "result",
  "command": "patch-status",
  "data": {
    "schema_version": "1",
    "pid": 12345,
    "timestamp": 1705586200.123,
    "monkey_patch": {
      "gevent": {
        "status": "active",
        "patched_modules": ["socket", "threading", "time", "select", "ssl"]
      },
      "eventlet": "not_imported"
    },
    "stdlib_origin": {
      "socket.socket": {
        "current_id": 140234567890,
        "native_id": 140234567800,
        "matches": false
      },
      "_socket.socket": {
        "current_id": 140234567800,
        "native_id": 140234567800,
        "matches": true
      },
      "_thread.start_new_thread": {
        "current_id": 140234568900,
        "native_id": 140234568800,
        "matches": false
      },
      "threading.RLock": {
        "current_id": 140234569900,
        "native_id": 140234569900,
        "matches": true
      }
    },
    "asyncio_loop": {
      "running": false,
      "policy": "DefaultEventLoopPolicy",
      "loop_class": null
    },
    "thread_model": {
      "main_thread_id": 140234560000,
      "total_threads": 5,
      "daemon_threads": 3,
      "classification": "multi_threaded_with_daemons"
    },
    "rpl_integrity": {
      "status": "ok",
      "ok": true,
      "socket_native": true,
      "thread_native": true,
      "lock_native": true,
      "rlock_native": true,
      "event_native": true,
      "time_native": true,
      "perf_counter_native": true,
      "get_ident_native": true,
      "captured_at_import": true
    }
  }
}
```

#### 步骤 2: 解读输出

**monkey_patch 部分**：
- `gevent.status = "active"`: gevent 已导入且已激活 monkey-patching
- `patched_modules`: gevent 替换了 5 个标准库模块（socket, threading, time, select, ssl）
- `eventlet = "not_imported"`: eventlet 未导入

**stdlib_origin 部分**：
- `socket.socket.matches = false`: Python 层 `socket.socket` 已被 gevent 替换（ID 不匹配）
- `_socket.socket.matches = true`: C 层 `_socket.socket` 仍然是原生的（gevent 不 patch C 扩展）
- `_thread.start_new_thread.matches = false`: 原生线程创建函数已被替换
- `threading.RLock.matches = true`: RLock 未被 patch（gevent 保留了这个）

**rpl_integrity 部分**：
- `status = "ok"`, `ok = true`: Peeka 的 Runtime Primitive Layer (RPL) 完整性正常
- 所有 8 个原生 primitive 检查都通过（`*_native = true`）
- `captured_at_import = true`: RPL 在模块导入时成功捕获了原生引用

**线程模型部分**：
- `total_threads = 5`: 进程有 5 个线程（包括 main thread + gevent hub + Peeka agent 线程）
- `daemon_threads = 3`: 其中 3 个是 daemon 线程
- `classification = "multi_threaded_with_daemons"`: 多线程 + daemon 线程混合模型

### 根因分析

**为什么 RPL 完整性检查通过？**

Peeka 的 agent 使用 Runtime Primitive Layer (RPL) 来绕过 monkey-patching：

1. **Eager Capture**: RPL 在模块导入时（`import peeka.core.runtime.primitives`）就捕获了原生 primitive 的引用，早于任何 monkey-patching
2. **C 扩展安全**: RPL 使用 `_socket.socket`（C 扩展）而非 `socket.socket`（Python 包装器）— gevent 只 patch Python 层
3. **原生线程**: RPL 使用 `_thread.start_new_thread`（原生 OS 线程）而非 `threading.Thread`（可能被 patch 的协程）

即使目标进程被 gevent 全面 patch，Peeka 仍然能：
- 创建真实的 OS 线程（非 greenlet）
- 使用阻塞的 socket I/O（非协程）
- 获取精确的时间戳（非 gevent 虚拟时间）

### 检查点解读

当 `rpl_integrity.ok = true` 时，表示：
- Peeka 的 agent 基础设施能安全运行（不会被 gevent/eventlet 干扰）
- `watch`, `trace`, `stack` 等命令可以正常工作
- Agent 和 CLI 之间的通信不会被 greenlet 调度器阻塞

当 `rpl_integrity.ok = false` 时，表示：
- RPL 未能成功捕获某些原生 primitive（可能在 RPL 导入前就被 patch 了）
- 部分 Peeka 功能可能不稳定
- 建议重新 attach 或检查 Python 环境

### 实际场景示例

**场景 A: 纯 gevent 应用**
```json
"monkey_patch": {
  "gevent": {"status": "active", "patched_modules": ["socket", "threading", ...]},
  "eventlet": "not_imported"
},
"rpl_integrity": {"status": "ok", "ok": true}
```
解读：gevent 已 patch，但 RPL 完整 → Peeka 可安全使用

**场景 B: 未 patch 的常规应用**
```json
"monkey_patch": {
  "gevent": "not_imported",
  "eventlet": "not_imported"
},
"stdlib_origin": {
  "socket.socket": {"matches": true},
  "_thread.start_new_thread": {"matches": true}
}
```
解读：无 monkey-patching → Peeka 和 stdlib 使用相同的 primitive

**场景 C: gevent 和 eventlet 混用（罕见但存在）**
```json
"monkey_patch": {
  "gevent": {"status": "imported_not_active"},
  "eventlet": {"status": "active"}
}
```
解读：gevent 已导入但未激活，eventlet 已激活 → 只有 eventlet 的 patch 生效

### 清理步骤

```bash
peeka-cli detach
kill 12345
```

### 相关文档

- [Runtime Primitive Layer](runtime-primitive-layer.md) — RPL 的设计原理和 API 文档
- [Python Process Attach Internals](python-process-attach-internals.md) — Peeka 如何注入代码到运行中的进程

---

## 附录：常用命令速查表

### 基础命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `attach <pid>` | 附加到进程 | `peeka-cli attach 12345` |
| `detach` | 从当前进程分离 | `peeka-cli detach` |
| `reset [pattern]` | 清除注入（不带参数清除全部） | `peeka-cli reset` |

### 观察命令

| 命令 | 说明 | 关键参数 |
|------|------|----------|
| `watch '<pattern>'` | 观察函数调用 | `-n` 次数, `--condition` 过滤条件 |
| `trace '<pattern>'` | 追踪直接子调用 | `--min-duration` 最小耗时 |
| `stack '<pattern>'` | 捕获调用栈 | `-n` 次数, `--depth` 栈深度 |
| `monitor '<pattern>'` | 周期性统计调用次数和耗时 | `--interval` 周期秒数, `-c` 周期数 |
| `top` | 整个进程的栈采样热点 | `--interval` 采样间隔, `--cycles` 周期数 |

### 内存分析

| 命令 | 说明 |
|------|------|
| `memory --action start` | 启动内存追踪（必须第一步） |
| `memory --action top --limit N` | 查看内存分配热点 |
| `memory --action snapshot` | 创建内存快照 |
| `memory --action diff` | 对比两次快照 |
| `memory --action stop` | 停止内存追踪 |

### 探索命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `sc '<pattern>'` | 搜索类 | `peeka-cli sc '__main__.*Service'` |
| `sm '<class pattern>'` | 列出类的方法 | `peeka-cli sm '__main__.UserService'` |
| `inspect --target <path>` | 按路径读取对象 | `peeka-cli inspect --target '__main__.config'` |
| `inspect --action instances --type <class>` | 列出类的存活实例 | `peeka-cli inspect --action instances --type '__main__.CacheManager'` |

### 日志管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `logger --action list` | 列出所有 logger | `peeka-cli logger --action list` |
| `logger --action set` | 调整日志级别 | `peeka-cli logger --action set --logger __main__ --level DEBUG` |

### 线程分析

| 命令 | 说明 |
|------|------|
| `thread` | 列出所有线程及其栈顶帧 |
| `thread --tid <tid>` | 查看单个线程的完整调用栈 |

### JSONL 输出类型

所有命令输出 JSONL 格式（每行一个 JSON 对象），通过 `type` 字段区分：

- `status`: 状态信息（非关键）
- `success`: 命令成功
- `error`: 命令失败
- `event`: 控制事件（started/stopped）
- `observation`: 实时观察数据（watch/stack/monitor）
- `result`: 查询结果（logger/memory/sc/sm）

### 使用 jq 过滤输出

```bash
# 只显示观察数据
peeka-cli watch '__main__.func' | jq 'select(.type == "observation")'

# 只显示耗时 > 100ms 的调用（cost 单位为毫秒）
peeka-cli watch '__main__.func' | jq 'select(.type == "observation" and .cost > 100)'

# 提取函数名和耗时
peeka-cli watch '__main__.func' | jq 'select(.type == "observation") | {func: .func_name, ms: .cost}'
```

---

## 总结

本教程展示了 8 个典型的 Python 运行时诊断场景：

1. **业务逻辑 Bug**：使用 `watch` 观察函数参数和返回值，定位计算错误
2. **慢请求**：使用 `monitor` + `watch --condition` + `trace` 渐进式定位性能瓶颈
3. **CPU 过高**：使用 `top` 采样热点函数，`trace` 分析时间分布
4. **内存泄漏**：使用 `memory` 命令完整工作流（start → top → snapshot → diff）
5. **死锁**：使用 `thread` 和 `thread --tid` 识别循环等待
6. **紧急诊断**：使用 `sc/sm/inspect/logger` 探索未知应用
7. **调用分析**：使用 `stack` 和 `watch` 识别高频调用方
8. **Monkey-Patch 检测**：使用 `patch-status` 确认 gevent/eventlet 状态和 RPL 完整性

所有示例脚本位于 `examples/scenario_*.py`，可直接运行和调试。

**关键原则**：
- 先 attach，再执行命令
- 内存分析必须先 `memory --action start`
- 使用 `--condition` 过滤高价值数据
- 结合 jq 处理 JSONL 输出
- 诊断完成后记得 `reset` 和 `detach`

Happy debugging with Peeka!

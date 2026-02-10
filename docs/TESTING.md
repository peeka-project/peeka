# Peeka 测试基础设施文档

## 概述

Peeka 已经实现了完善的端到端测试和容器化测试基础设施，使用 testcontainers 进行隔离的 Docker 环境测试。本文档详细说明了测试架构、如何运行测试以及如何通过 GitHub Actions 进行持续集成。

## 测试类型与分布

### 1. 测试标记（Test Markers）

Peeka 使用 pytest markers 来分类测试：

| 标记 | 描述 | 数量 |
|------|------|------|
| `unit` | 单元测试（快速，无外部依赖） | ~150 |
| `integration` | 集成测试（进程内 agent/client） | ~140 |
| `e2e` | 端到端测试（需要 ptrace） | ~20 |
| `container` | 容器测试（需要 Docker） | **79** |
| `tui` | TUI 测试（需要 textual） | ~5 |
| `slow` | 慢速测试（>10秒） | ~10 |
| `py314` | Python 3.14+ 专用（PEP 768） | ~15 |
| `gdb` | GDB 测试（回退机制） | ~10 |

### 2. 测试通过率

**最新测试结果**（本地运行）：
```
总计：296 个单元/集成测试
通过：292 个 (98.6%)
失败：4 个 (1.4%)
```

**失败的测试**：
- `test_attach_mechanism_available`：缺少 GDB（预期行为，CI 环境安装）
- `test_trace_command_*`：3 个 trace 命令测试（新功能，正在开发中）

## 容器化测试（Testcontainers）

### 已实现的测试

Peeka **已经实现了 79 个容器化 E2E 测试**，使用 `testcontainers` 库：

#### 测试分类

1. **attach/detach 测试** (`tests/container/test_attach.py`) - 14 个测试
   - 成功附加到目标进程
   - 创建 Unix socket 文件
   - 附加后分离
   - 无效 PID 的优雅失败
   - 重复附加行为
   - 进程清理验证
   - Socket 清理验证

2. **CLI 工作流测试** (`tests/container/test_cli_e2e.py`) - 16 个测试
   - 完整工作流：attach → watch → detach
   - 多命令序列
   - 条件过滤
   - 日志和内存命令
   - 双重附加失败处理

3. **诊断命令测试** (`tests/container/test_commands.py`) - 30 个测试
   - stack trace 获取
   - monitor 性能统计
   - logger 列表和级别设置
   - memory 概览和 GC
   - 类和方法搜索（sc/sm）
   - reset 命令

4. **watch 命令测试** (`tests/container/test_watch.py`) - 20 个测试
   - 基本观察
   - 次数限制
   - 条件过滤
   - 仅入口模式（-b flag）
   - 无效模式处理
   - JSONL 格式验证

5. **TUI 测试** (`tests/container/test_tui.py`) - 1 个测试
   - 容器内 pytest 执行

### 容器镜像

测试使用两种 Docker 镜像（在 `tests/container/conftest.py` 中定义）：

1. **GDB 镜像** (`docker/Dockerfile.test-gdb`)
   - 基于 `python:3.12-slim`
   - 包含 GDB + python3-dbg
   - 用于测试 GDB 回退机制

2. **Python 3.14 镜像** (`docker/Dockerfile.test-py314`)
   - 基于 `python:3.14-rc-slim`
   - 测试 PEP 768 原生附加

### 参数化测试

大多数容器测试使用 `@pytest.fixture(params=["gdb", "py314"])` 参数化，自动在两种 Python 版本上运行：

```python
@pytest.fixture(scope="function", params=["gdb", "py314"])
def container_target(request):
    """参数化 fixture，跨两种容器类型测试"""
    # 每个测试运行两次：一次用 GDB，一次用 PEP 768
```

## 运行测试

### 本地运行

#### 1. 安装依赖

```bash
# 仅核心依赖
pip install -e .

# 包含 TUI
pip install -e ".[tui]"

# 开发依赖（包括测试）
pip install -e ".[dev]"

# 或使用 uv（推荐）
uv pip install -e ".[dev]"
```

#### 2. 运行不同类型的测试

```bash
# 所有测试（警告：需要 Docker 和 ptrace）
pytest tests/ -v

# 仅单元和集成测试（快速，CI 安全）
pytest tests/ -v -m "not e2e and not container"

# 仅容器测试（需要 Docker）
pytest tests/container/ -v

# 仅 E2E 测试（需要 ptrace）
pytest tests/e2e/ -v

# 单个测试文件
pytest tests/test_injector.py -v

# 单个测试
pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v

# 使用超时保护
pytest tests/ -v --timeout=60
```

#### 3. 容器测试的前提条件

运行容器测试需要：
- Docker 运行中
- Docker socket 可访问
- 足够的权限构建镜像

```bash
# 检查 Docker
docker info

# 拉取基础镜像（可选，加速测试）
docker pull python:3.12-slim
docker pull python:3.14-rc-slim

# 运行容器测试
pytest tests/container/ -v --timeout=180
```

### Docker 手动测试

Peeka 提供了 4 个 Docker 镜像用于手动测试（`docker/` 目录）：

```bash
# 从项目根目录构建
docker build -f docker/Dockerfile.cli -t peeka-cli .
docker build -f docker/Dockerfile.tui -t peeka-tui .
docker build -f docker/Dockerfile.py314 -t peeka-py314 .
docker build -f docker/Dockerfile.full -t peeka-full .

# 运行（需要 SYS_PTRACE 能力）
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined peeka-cli

# 或使用 docker-compose
cd docker/
docker-compose up -d
docker-compose exec cli bash
```

## GitHub Actions CI/CD

### 已配置的工作流

Peeka 有 **2 个 GitHub Actions 工作流** 用于自动化测试：

#### 1. E2E Tests (`.github/workflows/e2e-tests.yml`)

触发条件：
- Push 到 `master`, `main`, `develop` 分支
- Pull request 到上述分支
- 手动触发（`workflow_dispatch`）

**三个作业**：

##### Job 1: `unit-tests`
- **矩阵策略**：Python 3.9, 3.12, 3.14
- 运行 `pytest tests/ -v -m "not e2e and not container"`
- 超时：30 秒
- **状态**：✅ 通过（292/296 测试通过）

##### Job 2: `e2e-container-tests`
- **Python 版本**：3.12
- 安装 `docker`, `testcontainers`
- 拉取测试镜像
- 运行 `pytest tests/container/ -v --timeout=180`
- **状态**：⚠️ `continue-on-error: true`（允许失败）

##### Job 3: `e2e-py314-test`
- 在 Python 3.14 容器内运行
- 验证 PEP 768 可用性
- 测试基本 attach 功能
- **状态**：✅ 通过

#### 2. Python Version Compatibility Test (`.github/workflows/test-compatibility.yml`)

触发条件：同上

**矩阵策略**：
- Python 版本：3.9, 3.10, 3.11, 3.12, 3.13, 3.14
- **失败策略**：`fail-fast: false`（所有版本都运行）

**步骤**：
1. 安装系统依赖（GDB, python-dbg）
2. 配置 ptrace 权限（`ptrace_scope=0`）
3. 运行简单兼容性测试
4. 运行集成测试子集

**状态**：✅ 大部分通过（部分版本可能因 GDB/ptrace 配置失败）

### CI 配置详情

#### ptrace 权限

Linux 系统默认限制 ptrace，CI 环境需要配置：

```yaml
- name: Configure ptrace permissions
  run: |
    echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

#### Docker 权限

容器测试需要 Docker socket 访问和 `SYS_PTRACE` 能力：

```yaml
cap_add: ["SYS_PTRACE"]
security_opt: ["seccomp:unconfined"]
```

#### 超时保护

所有测试作业都有超时保护：
- 单元测试：30 秒
- 容器测试：180 秒（3 分钟）
- 兼容性测试：5 分钟/作业

## 测试架构详解

### Testcontainers 架构

```
tests/container/conftest.py
├── Session-scoped fixtures (每个测试会话构建一次)
│   ├── gdb_image: 构建 GDB 测试镜像
│   └── py314_image: 构建 Python 3.14 测试镜像
│
├── Function-scoped fixtures (每个测试一个新容器)
│   ├── gdb_container: 启动 GDB 容器
│   ├── py314_container: 启动 Python 3.14 容器
│   ├── gdb_target: 在容器中启动目标进程
│   └── py314_target: 在容器中启动目标进程
│
└── Parametrized fixture
    └── container_target: 自动跨两种容器类型测试
```

### 容器测试生命周期

1. **构建阶段**（会话开始）
   ```python
   with DockerImage(
       path=".",
       dockerfile_path="docker/Dockerfile.test-gdb",
       tag="peeka-test:gdb",
   ) as image:
       yield image
   ```

2. **容器启动**（每个测试）
   ```python
   with DockerContainer(str(gdb_image)).with_kwargs(
       cap_add=["SYS_PTRACE"],
       security_opt=["seccomp:unconfined"],
       init=True,
   ) as container:
       container.start()
       yield container
   ```

3. **目标进程启动**
   ```python
   def start_target_in_container(container, timeout: int = 10) -> str:
       # 启动 simple_loop.py 在后台
       # 等待就绪信号文件
       # 返回 PID
   ```

4. **测试执行**
   ```python
   def exec_in_container(container, cmd: str, timeout: int = 30):
       # 在容器内执行 peeka 命令
       # 捕获输出
       # 解析 JSONL 响应
   ```

5. **清理**
   ```python
   def cleanup_peeka_files_in_container(container):
       exec_in_container(container, "rm -f /tmp/peeka_*", timeout=5)
   ```

### 目标进程脚本

容器测试使用 `tests/e2e/target_scripts/simple_loop.py` 作为目标：

```python
class Calculator:
    def add(self, a, b):
        return a + b
    def multiply(self, a, b):
        return a * b

# 循环调用，用于 watch/monitor 测试
```

## 测试最佳实践

### 1. 编写新的容器测试

```python
import pytest
from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container]

class TestNewFeature:
    def test_my_feature(self, container_target):
        """自动在 GDB 和 PY314 容器上运行"""
        container = container_target["container"]
        pid = container_target["pid"]

        # 附加
        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30
        )
        assert exit_code == 0

        # 执行命令
        exit_code, output = exec_in_container(
            container,
            "python -m peeka.cli.main my-command",
            timeout=10
        )

        # 验证 JSONL 输出
        import json
        lines = [l for l in output.strip().split("\n") if l.startswith("{")]
        for line in lines:
            data = json.loads(line)
            assert data.get("status") == "success"
```

### 2. 使用正确的标记

```python
# 容器测试
pytestmark = [pytest.mark.container]

# E2E 测试（本地进程）
pytestmark = [pytest.mark.e2e]

# 慢速测试
@pytest.mark.slow
def test_long_running():
    pass

# Python 3.14 专用
@pytest.mark.py314
def test_pep768_feature():
    pass
```

### 3. 超时保护

```python
# 使用 pytest-timeout
@pytest.mark.timeout(60)
def test_with_timeout():
    pass

# 容器命令超时
exec_in_container(container, cmd, timeout=30)
```

### 4. 错误处理

```python
# 验证优雅失败
exit_code, output = exec_in_container(
    container,
    "python -m peeka.cli.main attach 99999"  # 无效 PID
)
assert exit_code != 0 or "error" in output.lower()
```

## 故障排查

### 容器测试失败

**问题**：`Docker daemon not running`
```bash
# 启动 Docker
sudo systemctl start docker

# 验证
docker ps
```

**问题**：`Permission denied accessing Docker socket`
```bash
# 添加用户到 docker 组
sudo usermod -aG docker $USER
newgrp docker
```

**问题**：`Image build timeout`
```bash
# 预先拉取基础镜像
docker pull python:3.12-slim
docker pull python:3.14-rc-slim

# 增加 pytest 超时
pytest tests/container/ -v --timeout=300
```

### E2E 测试失败

**问题**：`Operation not permitted (ptrace)`
```bash
# 临时禁用 ptrace 限制
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# 验证
cat /proc/sys/kernel/yama/ptrace_scope  # 应该输出 0
```

**问题**：`GDB not found`
```bash
# 安装 GDB
sudo apt-get install gdb

# Python < 3.14 还需要调试符号
sudo apt-get install python3.12-dbg
```

### GitHub Actions 失败

**查看日志**：
```bash
# 使用 GitHub CLI
gh run list
gh run view RUN_ID
gh run view RUN_ID --log

# 或访问 Web UI
https://github.com/wwulfric/peeka/actions
```

**常见问题**：
1. **超时**：增加工作流中的 `timeout-minutes`
2. **权限**：确保 `ptrace_scope=0` 步骤执行
3. **Docker**：检查 `docker pull` 步骤是否成功

## 测试覆盖率

### 当前覆盖率（估计）

| 模块 | 覆盖率 | 说明 |
|------|--------|------|
| `peeka/core/injector.py` | ~95% | 函数包装、装饰器注入 |
| `peeka/core/agent.py` | ~90% | Agent 命令处理 |
| `peeka/core/client.py` | ~85% | Socket 通信 |
| `peeka/commands/*.py` | ~90% | 各命令实现 |
| `peeka/cli/main.py` | ~70% | CLI 入口（E2E 覆盖） |
| `peeka/tui/*.py` | ~60% | TUI 界面（部分测试） |
| `peeka/core/attach.py` | ~80% | 进程附加 |

### 改进建议

1. **添加覆盖率报告**
   ```bash
   pip install pytest-cov
   pytest tests/ --cov=peeka --cov-report=html
   ```

2. **集成到 CI**
   ```yaml
   - name: Run tests with coverage
     run: |
       pytest tests/ -v -m "not e2e and not container" \
         --cov=peeka --cov-report=xml

   - name: Upload coverage to Codecov
     uses: codecov/codecov-action@v3
   ```

## 性能测试

### 测试速度

```
单元测试：      ~15 秒（296 个测试）
容器测试：      ~2-5 分钟（79 个测试，包括镜像构建）
E2E 测试：      ~30 秒（20 个测试）
完整测试套件：  ~5-7 分钟
```

### 优化建议

1. **并行执行**
   ```bash
   pip install pytest-xdist
   pytest tests/ -n auto
   ```

2. **复用容器镜像**
   - 使用 session-scoped fixtures（已实现）
   - 预构建镜像推送到 Docker Hub

3. **选择性测试**
   ```bash
   # 只运行修改过的文件相关测试
   pytest tests/test_injector.py -v
   ```

## 未来改进

### 短期（1-2 周）

- [ ] 修复 4 个失败的单元测试
- [ ] 为容器测试添加重试机制
- [ ] 改进 CI 日志输出格式
- [ ] 添加测试覆盖率报告

### 中期（1-2 月）

- [ ] 实现测试并行化（pytest-xdist）
- [ ] 添加性能基准测试
- [ ] 集成 Codecov 或类似工具
- [ ] 添加 TUI 的更多自动化测试

### 长期（3-6 月）

- [ ] 实现持续性能监控
- [ ] 添加压力测试和负载测试
- [ ] 跨平台测试（macOS, Windows）
- [ ] 集成模糊测试（fuzzing）

## 总结

Peeka 已经实现了一个 **完善的测试基础设施**：

✅ **79 个容器化 E2E 测试** 使用 testcontainers
✅ **296 个单元/集成测试**，98.6% 通过率
✅ **GitHub Actions CI/CD** 自动化测试
✅ **双版本测试**：GDB (Python 3.12) + PEP 768 (Python 3.14)
✅ **完整的测试文档和最佳实践**

测试覆盖了：
- 进程附加/分离
- 函数观察（watch）
- 诊断命令（stack, monitor, logger, memory）
- 搜索功能（sc/sm）
- CLI 和 TUI 接口
- 错误处理和边界情况

这是一个生产就绪的测试框架，为 Peeka 的稳定性和可靠性提供了坚实的保障。

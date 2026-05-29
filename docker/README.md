# Peeka Docker 测试镜像

本目录包含测试用 Dockerfile，供 `testcontainers` 自动化测试和手动验证使用。

镜像**不包含** peeka 代码，只提供基础运行环境。代码通过 volume mount 挂载，镜像内设置 `PYTHONPATH=/app`，
所以 Python 源码改动无需重新构建镜像即可生效。

注意：Python 3.8-3.13 的 GDB/LLDB attach 路径需要原生扩展 `peeka.core._inject`。
当前 Docker 测试矩阵覆盖其中的 3.8 和 3.12；自动化容器测试会在容器内执行
`python setup.py build_ext --inplace`，为当前容器 Python 构建扩展。Python 3.14+ 的 PEP 768 路径不需要该扩展。

## 命名约定

| 类型 | Dockerfile 命名 | 镜像标签命名 |
|------|----------------|--------------|
| 基础镜像 | `base.Dockerfile-<version>` | `peeka-base:<version>` |
| 测试镜像 | `test.Dockerfile-<version>` | `peeka-test:<version>` |

**构建顺序**: 对于 Python < 3.14 需要分两阶段构建：
1. 先构建基础镜像（包含 Python + GDB + python3-dbg）
2. 再构建测试镜像（基于基础镜像，安装 textual 依赖）

Python 3.14 使用官方基础镜像直接构建测试镜像，无需单独基础镜像。

## 镜像概览

| 镜像标签 | Dockerfile | Python | 附加机制 | 用途 |
|---------|------------|--------|---------|------|
| `peeka-base:3.8` | `base.Dockerfile-3.8` | 3.8 | GDB + ptrace | 基础镜像（Python 3.8 + gdb + python3-dbg）|
| `peeka-test:3.8` | `test.Dockerfile-3.8` | 3.8 | GDB + ptrace | 完整 E2E 测试（Python 3.8）|
| `peeka-base:3.12` | `base.Dockerfile-3.12` | 3.12 | GDB + ptrace | 基础镜像（Python 3.12 + gdb + python3-dbg）|
| `peeka-test:3.12` | `test.Dockerfile-3.12` | 3.12 | GDB + ptrace | 完整 E2E 测试（Python 3.12）|
| `peeka-test:3.14` | `test.Dockerfile-3.14` | 3.14 | PEP 768 `sys.remote_exec` | 原生 PEP 768 测试 |

所有镜像均使用 USTC 镜像源（中科大）加速 apt 和 pip 下载。

## 构建镜像

从项目根目录执行：

### 构建所有镜像

```bash
# 1. 构建基础镜像
docker build --network=host -f docker/base.Dockerfile-3.8 -t peeka-base:3.8 .
docker build --network=host -f docker/base.Dockerfile-3.12 -t peeka-base:3.12 .

# 2. 构建测试镜像
docker build --network=host -f docker/test.Dockerfile-3.8 -t peeka-test:3.8 .
docker build --network=host -f docker/test.Dockerfile-3.12 -t peeka-test:3.12 .
docker build --network=host -f docker/test.Dockerfile-3.14 -t peeka-test:3.14 .
```

### 构建指定 Python 版本

```bash
# Python 3.8 (需要先构建基础)
docker build --network=host -f docker/base.Dockerfile-3.8 -t peeka-base:3.8 .
docker build --network=host -f docker/test.Dockerfile-3.8 -t peeka-test:3.8 .

# Python 3.12 (需要先构建基础)
docker build --network=host -f docker/base.Dockerfile-3.12 -t peeka-base:3.12 .
docker build --network=host -f docker/test.Dockerfile-3.12 -t peeka-test:3.12 .

# Python 3.14 (直接构建，无需单独基础)
docker build --network=host -f docker/test.Dockerfile-3.14 -t peeka-test:3.14 .
```

### 重新构建（无缓存，从 scratch 开始）

```bash
docker build --network=host --no-cache -f docker/base.Dockerfile-<version> -t peeka-base:<version> .
docker build --network=host --no-cache -f docker/test.Dockerfile-<version> -t peeka-test:<version> .
```

## 手动运行（volume mount 方式）

```bash
# Python 3.8 GDB 容器（挂载宿主机代码目录到 /app）
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v $(pwd):/app peeka-test:3.8

# Python 3.12 GDB 容器
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v $(pwd):/app peeka-test:3.12

# PEP 768 Python 3.14 容器
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v $(pwd):/app peeka-test:3.14
```

进入 Python 3.8-3.13 GDB/LLDB 环境后，第一次 attach 前需要构建 `_inject`。
当前手动测试容器覆盖 Python 3.8 和 3.12：

```bash
cd /app
python setup.py build_ext --inplace
```

## 自动化测试（testcontainers）

容器测试位于 `tests/container/`，由 pytest + testcontainers 自动管理容器生命周期。
conftest.py 会自动挂载宿主机项目目录到 `/app`，通过 `PYTHONPATH=/app` 使用挂载的 Python 代码；
对当前矩阵中的 Python 3.8/3.12 GDB 容器，还会在容器内自动构建 `_inject`。

```bash
# 运行全部容器测试
uv run pytest tests/container/test_attach.py -v -m container --timeout=180

# 仅运行指定 Python 版本测试
uv run pytest tests/container/test_attach.py -v -k "py38"
uv run pytest tests/container/test_attach.py -v -k "gdb"
uv run pytest tests/container/test_attach.py -v -k "py314"
```

### 容器内手动测试

```bash
# 启动测试目标进程
python examples/demo.py --mode loop &

# 附加到进程
python -m peeka.cli attach $(pgrep -f demo.py)

# 观测函数调用
python -m peeka.cli watch 'demo.Calculator.add' -n 5

# 追踪调用栈
python -m peeka.cli stack 'demo.Calculator.add' -n 2

# 搜索类
python -m peeka.cli sc 'Calculator'
```

## 网络说明

构建时必须使用 `--network=host`。原因：本机运行 Clash 代理（`127.0.0.1:7897`），
DNS 会将域名解析为 `198.18.x.x` 段的 fake-IP，Docker 隔离网络无法路由到 Clash。
使用 `--network=host` 共享宿主机网络栈即可正常访问 USTC 镜像源。

注意：Dockerfile 内部**不使用任何代理环境变量**（`http_proxy`/`https_proxy`），
仅通过 USTC 镜像源直接下载。

## 终端环境变量（TUI 必需）

所有测试镜像已在 Dockerfile 中内置 `TERM=xterm-256color` 和 `COLORTERM=truecolor`，
`docker exec` 进入容器后 TUI 可直接使用，无需额外设置。

## 目录结构

```
docker/
├── base.Dockerfile-3.8      # 基础镜像（Python 3.8 + gdb + python3-dbg）
├── base.Dockerfile-3.12     # 基础镜像（Python 3.12 + gdb + python3-dbg）
├── test.Dockerfile-3.8      # 测试镜像（基于 peeka-base:3.8）
├── test.Dockerfile-3.12     # 测试镜像（基于 peeka-base:3.12）
├── test.Dockerfile-3.14     # 测试镜像（Python 3.14 原生 PEP 768）
├── restart-demo.sh           # 容器启动脚本：自动运行 demo 进程
└── README.md
```

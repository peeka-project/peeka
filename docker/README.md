# Peeka Docker 测试镜像

本目录包含测试用 Dockerfile，供 `testcontainers` 自动化测试和手动验证使用。

镜像**不包含** peeka 代码，只提供基础运行环境。代码通过 volume mount 挂载，镜像内设置 `PYTHONPATH=/app`，
无需 pip install 即可直接使用。只要镜像存在就能反映最新代码，无需重新构建。

## 镜像概览

| 镜像标签 | Dockerfile | Python | 附加机制 | 用途 |
|---------|------------|--------|---------|------|
| `python:3.12-trixie-gdb` | `Dockerfile.python312-trixie-gdb` | 3.12 | GDB + ptrace | 基础镜像（Python 3.12 + gdb + python3-dbg）|
| `peeka-test:gdb` | `Dockerfile.test-gdb` | 3.12 | GDB + ptrace | 旧版 Python 附加测试 |
| `peeka-test:py314` | `Dockerfile.test-py314` | 3.14 | PEP 768 `sys.remote_exec` | 原生远程调试测试 |

两个测试镜像均使用 USTC 镜像源（中科大）加速 apt 和 pip 下载。

## 构建镜像

从项目根目录执行：

```bash
# 1. 构建基础镜像（peeka-test:gdb 依赖此镜像）
docker build --network=host -f docker/Dockerfile.python312-trixie-gdb -t python:3.12-trixie-gdb .

# 2. 构建 GDB 测试镜像
docker build --network=host -f docker/Dockerfile.test-gdb -t peeka-test:gdb .

# 3. 构建 PEP 768 测试镜像
docker build --network=host -f docker/Dockerfile.test-py314 -t peeka-test:py314 .
```

## 手动运行（volume mount 方式）

```bash
# GDB 容器（挂载宿主机代码目录到 /app）
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v $(pwd):/app peeka-test:gdb

# PEP 768 容器
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v $(pwd):/app peeka-test:py314
```

## 自动化测试（testcontainers）

容器测试位于 `tests/container/`，由 pytest + testcontainers 自动管理容器生命周期。
conftest.py 会自动挂载宿主机项目目录到 `/app`，通过 `PYTHONPATH=/app` 直接使用挂载的代码。

```bash
# 运行全部容器测试
uv run pytest tests/container/test_attach.py -v -m container --timeout=180

# 仅运行 gdb 相关测试
uv run pytest tests/container/test_attach.py -v -k "gdb"

# 仅运行 py314 相关测试
uv run pytest tests/container/test_attach.py -v -k "py314"
```

### 容器内手动测试

```bash
# 启动测试目标进程
python examples/demo.py --mode loop &

# 附加到进程
python -m peeka.cli.main attach $(pgrep -f demo.py)

# 观测函数调用
python -m peeka.cli.main watch 'demo.Calculator.add' -n 5

# 追踪调用栈
python -m peeka.cli.main stack 'demo.Calculator.add' -n 2

# 搜索类
python -m peeka.cli.main sc 'Calculator'
```

## 网络说明

构建时必须使用 `--network=host`。原因：本机运行 Clash 代理（`127.0.0.1:7897`），
DNS 会将域名解析为 `198.18.x.x` 段的 fake-IP，Docker 隔离网络无法路由到 Clash。
使用 `--network=host` 共享宿主机网络栈即可正常访问 USTC 镜像源。

注意：Dockerfile 内部**不使用任何代理环境变量**（`http_proxy`/`https_proxy`），
仅通过 USTC 镜像源直接下载。

## 目录结构

```
docker/
├── Dockerfile.python312-trixie-gdb  # 基础镜像（Python 3.12 + gdb + python3-dbg）
├── Dockerfile.test-gdb              # GDB 测试镜像（基于 python:3.12-trixie-gdb）
├── Dockerfile.test-py314            # PEP 768 测试镜像（Python 3.14）
└── README.md
```

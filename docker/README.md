# Peeka Docker 测试镜像

本目录包含 2 个测试用 Dockerfile，供 `testcontainers` 自动化测试和手动验证使用。

## 镜像概览

| 镜像标签 | Dockerfile | Python | 附加机制 | 用途 |
|---------|------------|--------|---------|------|
| `peeka-test:gdb` | `Dockerfile.test-gdb` | 3.12 | GDB + ptrace | 旧版 Python 附加测试 |
| `peeka-test:py314` | `Dockerfile.test-py314` | 3.14 | PEP 768 `sys.remote_exec` | 原生远程调试测试 |

两个镜像均使用 USTC 镜像源（中科大）加速 apt 和 pip 下载。

## 自动化测试（testcontainers）

容器测试位于 `tests/container/`，由 pytest + testcontainers 自动管理镜像生命周期。

```bash
# 运行全部容器测试（14 个：7 gdb + 7 py314）
uv run pytest tests/container/test_attach.py -v -m container --timeout=180

# 仅运行 gdb 相关测试
uv run pytest tests/container/test_attach.py -v -k "gdb"

# 仅运行 py314 相关测试
uv run pytest tests/container/test_attach.py -v -k "py314"
```

测试 fixture 定义在 `tests/container/conftest.py`，自动构建镜像并启动容器。

## 手动构建与验证

从项目根目录执行：

```bash
# 构建 GDB 测试镜像
docker build --network=host -f docker/Dockerfile.test-gdb -t peeka-test:gdb .

# 构建 PEP 768 测试镜像
docker build --network=host -f docker/Dockerfile.test-py314 -t peeka-test:py314 .

# 运行容器（需要 ptrace 权限）
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined peeka-test:gdb
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined peeka-test:py314
```

### 容器内手动测试

```bash
# 启动测试目标进程
python examples/demo.py --mode loop &

# 附加到进程
peeka-cli attach $(pgrep -f demo.py)

# 观测函数调用
peeka-cli watch 'demo.Calculator.add' -n 5

# 追踪调用栈
peeka-cli stack 'demo.Calculator.add' -n 2

# 搜索类
peeka-cli sc 'Calculator'
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
├── Dockerfile.test-gdb     # GDB 测试镜像（Python 3.12 + gdb + python3-dbg）
├── Dockerfile.test-py314   # PEP 768 测试镜像（Python 3.14）
└── README.md               # 本文件
```

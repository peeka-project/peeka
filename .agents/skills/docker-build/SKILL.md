---
name: docker-build
description: 为 peeka E2E 测试构建 Docker 测试镜像。支持构建 gdb（Python 3.8/3.12）和 py314（Python 3.14 PEP 768）镜像。使用 --network=host 处理 fake-ip/tun 模式的网络代理问题。如果镜像已在本地存在则自动跳过构建。触发词："build docker", "create docker image", "docker-build", "build container image", "rebuild test images", "docker-build py38", "docker-build python3.8"。
---

# Docker 构建技能

为 peeka 端到端附加测试构建 Docker 测试镜像。本技能遵循标准化命名约定，处理 Python 版本 < 3.14 的两阶段构建。

## 命名标准化

**约定**：
| 类型 | Dockerfile 命名 | 镜像标签 |
|------|----------------|----------|
| 基础镜像 | `base.Dockerfile-<version>` | `peeka-base:<version>` |
| 测试镜像 | `test.Dockerfile-<version>` | `peeka-test:<version>` |

**构建规则**：
- Python **< 3.14**：两阶段构建 → 先构建基础镜像（含 GDB + python-dbg），再从基础镜像构建测试镜像
- Python **3.14+**：单阶段构建 → 直接使用官方 Python 镜像，无需单独基础镜像（PEP 768 原生支持）

## 支持的 Python 版本

| 版本 | 是否需要基础镜像 | 附加机制 | 用途 |
|------|----------------|----------|------|
| 3.8 | 是 | GDB + ptrace | 旧版 Python 兼容性测试 |
| 3.12 | 是 | GDB + ptrace | 主要 GDB 测试 |
| 3.14 | 否 | PEP 768 `sys.remote_exec` | 原生远程调试测试 |

## 网络问题背景

如果你使用代理（如 Clash）并启用 **tun 模式 + fake-ip DNS**：
1. Clash DNS 返回 `198.18.0.0/15` 范围内的 fake IP
2. Fake-ip 路由被添加到宿主机的路由表，指向 tun 接口
3. Docker **默认桥接网络**不会继承此路由
4. 结果：网络调用失败，因为容器无法路由 fake IP
5. **解决方案**：始终使用 `--network=host` 构建，共享宿主机网络栈（已有正确路由）

## 构建工作流程

### 检查镜像是否已存在

技能会自动检查镜像是否已存在：
```bash
docker inspect peeka-test:<version> >/dev/null 2>&1 && echo "镜像已存在"
```

如果镜像已存在，构建会被跳过——可以直接使用现有镜像。如果不存在，会自动构建。

### 构建所有支持的镜像（完整构建）：

```bash
# 先构建基础镜像
docker build --network=host -f docker/base.Dockerfile-3.8 -t peeka-base:3.8 .
docker build --network=host -f docker/base.Dockerfile-3.12 -t peeka-base:3.12 .

# 再构建测试镜像
docker build --network=host -f docker/test.Dockerfile-3.8 -t peeka-test:3.8 .
docker build --network=host -f docker/test.Dockerfile-3.12 -t peeka-test:3.12 .
docker build --network=host -f docker/test.Dockerfile-3.14 -t peeka-test:3.14 .
```

### 构建指定 Python 版本：

```bash
# Python 3.8
docker build --network=host -f docker/base.Dockerfile-3.8 -t peeka-base:3.8 .
docker build --network=host -f docker/test.Dockerfile-3.8 -t peeka-test:3.8 .

# Python 3.12
docker build --network=host -f docker/base.Dockerfile-3.12 -t peeka-base:3.12 .
docker build --network=host -f docker/test.Dockerfile-3.12 -t peeka-test:3.12 .

# Python 3.14
docker build --network=host -f docker/test.Dockerfile-3.14 -t peeka-test:3.14 .
```

### 从头重建（清除 Docker 缓存）：

```bash
docker build --network=host --no-cache -f docker/base.Dockerfile-<version> -t peeka-base:<version> .
docker build --network=host --no-cache -f docker/test.Dockerfile-<version> -t peeka-test:<version> .
```

## 构建后启动容器

构建完成后，用以下命令启动容器：

```bash
docker run -d --name peeka-test-<version> \
  --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --network=host \
  -v $(pwd):/app \
  peeka-test:<version>
```

容器会自动：
- 在后台启动 `examples/demo.py` 循环进程
- 设置正确的 TUI 环境变量（`TERM=xterm-256color`, `COLORTERM=truecolor`）
- 持续运行直到你停止它

完成后停止并删除：
```bash
docker stop peeka-test-<version> && docker rm peeka-test-<version>
```

## 验证构建

### 检查镜像是否存在：
```bash
docker images | grep peeka-
```

### 检查容器是否运行：
```bash
docker ps | grep peeka-test
```

### 检查容器内的 demo 进程：
```bash
docker exec peeka-test-<version> ps aux | grep demo.py
```

## 与 container-test 技能集成

本技能构建镜像，`container-test` 技能在运行中的容器内执行测试：

**完整工作流示例**：
```
1. 你："/docker-build 3.14"
   → 技能检查 peeka-test:3.14 是否存在 → 如果不存在则构建 → 完成
2. 你："/container-test 3.14"
   → 技能在运行中的容器内执行 E2E 测试
```

## 常见问题

### 构建时网络超时/失败
**原因**：Docker 默认桥接网络无法路由代理 tun 模式的 fake-ip。
**解决方案**：本技能已对所有构建使用 `--network=host`——这解决了该问题。

### 镜像已存在
**行为**：技能会自动检测现有镜像并跳过重建以节省时间。直接使用现有镜像即可。如果需要重建，使用 `--no-cache`。

### 连接 Docker 权限被拒绝
**原因**：用户不在 docker 组中。
**解决方案**：`sudo usermod -aG docker $USER` → 注销后重新登录。

### 已有容器在运行怎么办？
**行为**：如果需要用新代码重新启动，只需停止/删除旧容器并启动新容器：
```bash
docker stop peeka-test-<version> && docker rm peeka-test-<version>
# 然后重新启动
```

### 卷挂载不生效
**原因**：你没有在项目根目录运行命令。
**解决方案**：始终在**项目根目录**运行构建/启动命令，这样 `$(pwd):/app` 才能挂载正确的目录。

## 通过 Claude Code 调用命令

本技能在这些短语触发时激活：
- `/docker-build` → 检查/构建所有缺失的镜像
- `/docker-build 3.8` → 检查/构建 Python 3.8
- `/docker-build 3.12` → 检查/构建 Python 3.12
- `/docker-build 3.14` → 检查/构建 Python 3.14

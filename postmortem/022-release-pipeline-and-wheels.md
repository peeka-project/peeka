# 发布流水线与分发产物问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | PyPI 发布流水线、wheel 构建矩阵与 release gate 的工具版本漂移 |
| **受影响组件** | .github/workflows/publish-pypi.yml, .github/workflows/build-wheels.yml, pyproject.toml, setup.py |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 2 |
| **时间跨度** | 2026-11-07 至 2026-11-09 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#2](#事故-2ci-未锁定-ruff-版本导致-release-gate-失败) | CI 未锁定 ruff 版本导致 release gate 失败 | SEV-2 | 2026-11-09 |
| [#1](#事故-1pypi-长期只发布-glibc-234-单一-wheel) | PyPI 长期只发布 glibc 2.34 单一 wheel | SEV-1 | 2026-11-07 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题记录发布流水线本身的故障：构建矩阵依赖的 runner 标签被平台下线、发布工作流与 wheel 工作流各自构建产物、以及 CI 安装未锁定版本的工具。共同模式是**发布流水线对外部平台与工具版本做了隐式假设**，而这些假设只在 tag 推送时才被验证，失败成本高。

---

## 事故 #2：CI 未锁定 ruff 版本导致 release gate 失败

> **Tag 范围**：`v0.1.20` → `v0.1.21` | **严重级别**：SEV-2 | **日期**：2026-11-09

### 概要

推送 `v0.1.21` 后 publish 工作流的 Run Tests 失败：1516 个测试通过，但 `ruff check peeka/` 报告 1836 处问题。本地 ruff 0.15.14 检查通过。PyPI 尚未发布，修复后按 Case A 移动 tag 重新发布。

### 根因分析

#### 类别
Dependency Issue / Configuration Error

#### 分析
`publish-pypi.yml` 以 `pip install pytest pytest-timeout pytest-asyncio ruff` 安装依赖，ruff 不锁版本；项目也没有 `[tool.ruff]` 配置，完全依赖 ruff 的默认规则集。CI 安装到 ruff 0.17.4，ruff 0.16 起默认启用的规则大幅扩展（FA100、BLE001、S110、I001、UP0xx 等），导致同一份代码在本地与 CI 上结论不同。`uv.lock` 自 `cd60e87` 起不再被跟踪，本地版本也不再受锁文件约束，进一步降低了一致性。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `e19ff6a` | lufeihaidao | 2026-03-11 | feat(release): add PyPI publish workflow for automated releases |

### 复现

#### 步骤
1. `uvx ruff@0.15.14 check peeka/` → All checks passed。
2. `uvx ruff@0.17.4 check peeka/` → Found 1836 errors。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`5ec0fdd`](https://github.com/peeka-project/peeka/commit/5ec0fdd) | lufeihaidao | 2026-11-09 | fix(ci): pin ruff lint rules so newer ruff defaults don't break the release gate |

#### 变更内容
在 `pyproject.toml` 中新增 `[tool.ruff.lint] select = ["E4", "E7", "E9", "F"]`，把规则集固定为 ruff 0.15 的默认值，使任何 ruff 版本得到一致结论。随后将本地 `v0.1.21` tag 移到修复提交并强制推送。

#### 验证
ruff 0.15.14 与 0.17.4 均通过；`scripts/release_check.sh` 通过；重新触发的 publish 工作流成功发布。

### 影响

- **受影响用户**：无；发布被推迟约 15 分钟。
- **数据影响**：无（PyPI 发布前失败）。

### 经验教训

#### 可以改进的方面
- release gate 只在 tag 推送时运行，工具版本漂移无法在日常提交中提前暴露。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| CI 中 ruff、pytest 等工具锁定版本范围 | P1 | 待处理 |
| 在 master push 上运行与 release gate 相同的 lint 检查 | P2 | 待处理 |

### 预防

- **立即执行**：lint 规则集显式配置，不依赖工具默认值。
- **短期**：CI 依赖与 `pyproject.toml` 的 dev 依赖保持同一约束来源。

---

## 事故 #1：PyPI 长期只发布 glibc 2.34 单一 wheel

> **Tag 范围**：`v0.1.15` → `v0.1.21` | **严重级别**：SEV-1 | **日期**：2026-11-07

### 概要

v0.1.15 至 v0.1.20 的 Build Wheels 运行全部在 24 小时后被取消：每个 `macos-13` job 都在等待一个已被下线的 runner 标签。与此同时 publish-pypi 在 `ubuntu-latest` 上自行构建单个 wheel，PyPI 实际只收到 `cp312-cp312-manylinux_2_34_x86_64`（需要 GLIBC_2.34）和 sdist。其他 Python 版本、旧 glibc 容器与 macOS 用户只能走 sdist 编译，或在旧容器中 dlopen 注入扩展时报 `GLIBC_2.34 not found`。

### 根因分析

#### 类别
Configuration Error

#### 分析
- wheel 构建与发布是两套互不依赖的工作流，发布工作流不等待也不使用 Build Wheels 的产物，因此 Build Wheels 长期失败而无人察觉。
- `macos-13` runner 标签被 GitHub 下线后，job 无限排队直至超时取消，没有失败信号。
- 在现代主机上直接构建得到 `manylinux_2_34` wheel，而注入扩展需要在目标容器（如 Debian 系 `python:3.8` 镜像）内被 dlopen，要求更低的 glibc 基线。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `1bd8d3e` | lufeihaidao | 2026-04-26 | feat(packaging): add C extension package-data, wheel CI workflow, and macOS LLDB support |

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`341fd6c`](https://github.com/peeka-project/peeka/commit/341fd6c) | lufeihaidao | 2026-11-07 | fix(ci): build abi3 wheels with cibuildwheel and publish them to PyPI |
| [`82c4dcf`](https://github.com/peeka-project/peeka/commit/82c4dcf) | lufeihaidao | 2026-11-08 | fix(ci): use macos-latest and fix manylinux wheel name check |

#### 变更内容
- `_inject.c` 只使用稳定 ABI 符号且不依赖 `Python.h`，在所有非 free-threaded CPython（含 3.8）上构建为 `cp38-abi3`。
- `[tool.cibuildwheel]` 构建一次 cp38、在 cp314 上复测，Linux 使用 manylinux2014（glibc 2.17）镜像。
- `build-wheels.yml` 改为可复用工作流（ubuntu x86_64 / arm aarch64 / macOS arm64 + 交叉编译 x86_64），断言 Linux wheel 为 `manylinux_2_17`；publish-pypi 调用它并上传全部 wheel 与 sdist；所有 job 增加超时。

#### 验证
v0.1.21 发布时 PyPI 收到 6 个 cp38-abi3 wheel（macOS x86_64/arm64、manylinux2014 x86_64/aarch64、musllinux x86_64/aarch64）和 sdist。

### 影响

- **受影响用户**：v0.1.15–v0.1.20 期间非 cp312/x86_64/新 glibc 环境的用户，以及向旧 glibc 容器注入的用户。
- **持续时间**：约 6 个版本。
- **数据影响**：无。

### 经验教训

#### 可以改进的方面
- 被取消（cancelled）的工作流不会像失败一样引起注意；发布产物清单从未被校验。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 发布后校验 PyPI 文件清单（wheel 平台标签与数量） | P1 | 待处理 |

### 预防

- **立即执行**：发布只使用经过校验的构建产物，工作流之间显式依赖。
- **短期**：所有 job 设置超时，避免无限排队。
- **长期**：定期审计 runner 标签与平台下线公告。

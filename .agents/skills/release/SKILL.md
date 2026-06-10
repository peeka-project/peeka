---
name: release
description: "Create a versioned release for peeka. Triggers: /release, version bump, publish to PyPI, create tag, github release, semver. Usage: /release <version|patch|minor|major>"
---

# Release Skill

Automate the complete release workflow for peeka: version updates, git commits, tags, push, and a concise GitHub Release description. GitHub Actions handles PyPI publishing and creates the initial GitHub Release; this skill must replace the generated commit-list notes with a short, user-facing summary.

## Prerequisites

Before using this skill, ensure the following are configured:

1. **GitHub CLI authenticated**:
   ```bash
   gh auth status
   # Must show an authenticated account with repo access.
   ```

2. **PyPI Trusted Publisher** configured on pypi.org:
   - Add the repository reported by `gh repo view --json nameWithOwner --jq .nameWithOwner` as a trusted publisher
   - GitHub environment: `pypi` (uses OIDC token exchange, no secrets needed)

3. **Clean working directory**:
   - All changes committed
   - On `master` branch
   - No version drift between `pyproject.toml` and `peeka/__init__.py`

4. **Repository identity resolved from the local checkout**:
   ```bash
   repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
   # Expected for this repository: peeka-project/peeka
   ```
   Do not hard-code a personal fork name in release commands. Use `repo_full_name` for `gh release`, `gh run`, and GitHub URLs.

## Quick Reference

```bash
# Version bump by type
/release patch  # 0.1.0 → 0.1.1
/release minor  # 0.1.0 → 0.2.0
/release major  # 0.1.0 → 1.0.0

# Explicit version
/release 0.2.0

# Verify on PyPI (after workflow completes)
pip index versions peeka
```

## Workflow Overview

The release process consists of 6 phases executed sequentially. Each phase must succeed before proceeding to the next.

```
Phase 1: Parse & Validate Input
  ↓
Phase 2: Pre-release Postmortem Check (regression prevention gate)
  ↓
Phase 3: Update Version Files
  ↓
Phase 4: Commit, Tag, Push
  ↓
Phase 5: Post-Release Verification
  ↓
Phase 6: Post-release Postmortem Analysis
```

GitHub Actions automatically handles (triggered by tag push):
- Running tests
- Building and publishing to PyPI
- Creating an initial GitHub Release

The release agent must then update the GitHub Release body with a summarized, social-ready description. Do not leave the final release notes as a raw commit list.

**Total Duration**: ~5-15 minutes (depends on GitHub Actions queue and postmortem analysis scope)

---

## Phase 1: Parse & Validate Input

### 1.1 Parse Version Argument

Accept two input formats:

**Bump Type** (recommended):
- `patch` — Increment patch version (0.1.0 → 0.1.1)
- `minor` — Increment minor version (0.1.0 → 0.2.0)
- `major` — Increment major version (0.1.0 → 1.0.0)

**Explicit Version**:
- Format: `X.Y.Z` (three integers separated by dots)
- Example: `0.2.0`, `1.0.0`, `2.1.3`

### 1.2 Calculate New Version

**If bump type provided**:

1. Read current version from `pyproject.toml` line 7:
   ```bash
   current=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
   ```

2. Calculate next version:
   ```python
   # Parse current version
   major, minor, patch = current.split('.')
   
   # Bump appropriate component
   if bump_type == 'patch':
       patch += 1
   elif bump_type == 'minor':
       minor += 1
       patch = 0
   elif bump_type == 'major':
       major += 1
       minor = 0
       patch = 0
   
   new_version = f"{major}.{minor}.{patch}"
   ```

**If explicit version provided**:
- Validate format: must match regex `^\d+\.\d+\.\d+$`
- Use as-is

### 1.3 Validation Checks

Run all validation checks **BEFORE** making any changes:

#### Check 1: Version Format
```bash
# Validate X.Y.Z format
echo "0.2.0" | grep -qE '^\d+\.\d+\.\d+$'
if [ $? -ne 0 ]; then
    echo "Error: Invalid version format. Use X.Y.Z or patch/minor/major"
    exit 1
fi
```

#### Check 2: Version Must Increase
```bash
# Read current version
current=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)

# Compare versions (using Python for semantic comparison)
python3 -c "
from packaging.version import Version
current = Version('$current')
new = Version('$new_version')
if new <= current:
    print(f'Error: New version {new} must be greater than current {current}')
    exit(1)
"
```

**Exception — First release**: If the version in `pyproject.toml` matches the target version AND no git tag exists for it yet, this is a first release. Skip the "must increase" check and proceed directly to Phase 3 (no version file updates needed).

#### Check 3: Tag Does Not Exist
```bash
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)

# Check if tag already exists on remote
gh release view v$new_version --repo "$repo_full_name" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "Error: Release v$new_version already exists"
    exit 1
fi

git tag --list "v$new_version" | grep -q "v$new_version"
if [ $? -eq 0 ]; then
    echo "Error: Tag v$new_version already exists locally"
    exit 1
fi
```

#### Check 4: Clean Working Directory
```bash
# Ensure no uncommitted changes
status=$(git status --porcelain)
if [ -n "$status" ]; then
    echo "Error: Working directory has uncommitted changes:"
    echo "$status"
    echo ""
    echo "Commit or stash changes before releasing"
    exit 1
fi
```

#### Check 5: On Master Branch
```bash
# Verify current branch is master
current_branch=$(git branch --show-current)
if [ "$current_branch" != "master" ]; then
    echo "Error: Must be on master branch (currently on $current_branch)"
    exit 1
fi
```

#### Check 6: Version Files in Sync
```bash
# Read versions from both files
pyproject_version=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
init_version=$(grep '^__version__ = ' peeka/__init__.py | cut -d'"' -f2)

if [ "$pyproject_version" != "$init_version" ]; then
    echo "Error: Version mismatch between files:"
    echo "  pyproject.toml:     $pyproject_version"
    echo "  peeka/__init__.py:  $init_version"
    echo ""
    echo "Fix the mismatch before releasing"
    exit 1
fi
```

**Success Output**:
```
✓ Version format valid: 0.2.0
✓ Version increases: 0.1.0 → 0.2.0
✓ Tag v0.2.0 does not exist
✓ Working directory clean
✓ On master branch
✓ Version files in sync
```

### 1.4 Release Gate: Run the CI-equivalent Local Check

Before changing versions or creating tags, run the repository release gate:

```bash
bash scripts/release_check.sh
```

This script is the single source of truth for the release test gate. It runs the same non-container, non-e2e, non-TUI unit-test set as `.github/workflows/publish-pypi.yml`, plus `ruff check peeka/`.

Important details:
- Locally, the script uses `uv run` when `uv` is available, matching repository development rules.
- In GitHub Actions or minimal environments without `uv`, it falls back to the current Python environment.
- Tests must not hard-code `uv` in subprocess calls. CLI subprocess tests should use `sys.executable -m peeka.cli.main ...`.
- `tests/test_release_checks.py` enforces this for direct `subprocess.*(["uv", ...])` calls in tests.

For changes that touch attach, target routing, probes, consumers, DX cases, Docker images, or runtime compatibility, also run the relevant container/manual matrix before release. The default publish workflow does not run Docker or ptrace-dependent tests.

---

## Phase 2: Pre-release Postmortem Check

在版本文件更新之前，分析本次 release 包含的所有提交，检查是否触发了已有 postmortem 中记录的已知问题模式。这是一道**回归预防门禁**。

### 2.1 确定提交范围

```bash
# 找到上一个 release tag
previous_tag=$(git describe --tags --abbrev=0 HEAD 2>/dev/null)
# 如果没有 tag，使用整个历史
if [ -z "$previous_tag" ]; then
    previous_tag=$(git rev-list --max-parents=0 HEAD)
fi

# 获取范围内所有提交
git log $previous_tag..HEAD --pretty=format:"%H|%h|%s" --no-merges
```

### 2.2 加载已有 Postmortem 知识库

扫描 `./postmortem/` 目录中所有 `\d{3}-*.md` 话题文件，提取以下信息：

1. **根因模式**：每个事故的根因类别（Race Condition、Logic Error、Missing Validation 等）
2. **受影响组件**：每个话题涉及的模块/文件路径
3. **预防措施**：每个事故的"预防"和"行动项"章节
4. **关键代码模式**：事故中提到的具体代码反模式（如"并行刷新共享连接"、"worker.result 未包装 try/except"、"fail-open 异常处理"）

```bash
# 列出所有话题文件
ls ./postmortem/[0-9][0-9][0-9]-*.md 2>/dev/null
```

### 2.3 逐提交交叉比对

对范围内的**每个提交**，执行以下检查：

#### 检查 A：文件路径重叠

```bash
# 获取提交修改的文件
git diff-tree --no-commit-id --name-only -r <commit_hash>
```

将修改的文件路径与已有 postmortem 的"受影响组件"进行匹配。如果提交修改了某个 postmortem 话题中反复出现问题的模块（如 `peeka/tui/views/memory.py` 在 `002-tui-memory-view.md` 中有 13 次事故记录），标记为**高风险**。

#### 检查 B：代码模式匹配

对高风险提交，读取 diff 内容：

```bash
git show <commit_hash> --stat
git show <commit_hash> -- <file>
```

检查 diff 是否包含已有 postmortem 中记录的反模式：

| Postmortem 反模式 | 代码信号 |
|-------------------|----------|
| 并行刷新共享连接（002, 004） | 同一客户端的并发 `run_worker` / `asyncio.gather` |
| worker.result 未做异常处理（002, 005） | `worker.result` 或 `worker.wait()` 后无 try/except |
| fail-open 异常路径（014） | except 块中 return True 或无 return |
| CSS 特异性冲突（002, 012） | 新增 CSS 规则与已有规则同 specificity 竞争 |
| 线程安全未加锁（004, 006） | 共享可变状态无 `threading.Lock` |
| CLI ↔ Agent 参数键不一致（009） | CLI 端和 agent 端参数名称不匹配 |

#### 检查 C：提交消息语义分析

检查提交消息是否包含已有 postmortem 中反复出现的关键词组合：

```bash
# 示例关键词（从已有 postmortem 根因中提取）
# "thread" + "race" / "concurrent" / "shared"
# "socket" + "contention" / "broken"
# "mount" + "lifecycle" / "init order"
# "css" + "specificity" / "override"
```

### 2.4 生成风险报告

汇总所有发现，输出风险报告：

```
=== Pre-release Postmortem Check ===

Commits analyzed: N (from <previous_tag> to HEAD)

⚠ RISK FINDINGS:

[HIGH] Commit abc1234 "feat(tui): add parallel data loading"
  → Matches postmortem pattern from 002-tui-memory-view.md (事故 #9)
  → Pattern: 并行刷新共享连接
  → File: peeka/tui/views/dashboard.py
  → Recommendation: 确保不同数据源使用独立客户端连接，或串行化请求

[MEDIUM] Commit def5678 "refactor(tui): update memory view layout"
  → Touches high-risk module: peeka/tui/views/memory.py (13 历史事故)
  → Recommendation: 审查 CSS 特异性和生命周期处理

[LOW] Commit 789abcd "feat(cli): add new inspect subcommand"
  → Touches CLI dispatch (009-cli-commands-and-payloads.md)
  → Recommendation: 验证 CLI 参数键与 agent 端参数名一致

✓ No risks: 15 commits
```

### 2.5 处置决策

根据风险发现采取行动：

**无风险发现（常见）**：
```
✓ Pre-release postmortem check passed — no known regression patterns detected
```
直接进入 Phase 3。

**存在风险发现**：

1. 将风险报告呈现给用户
2. 对每个 HIGH 级别发现，**询问用户**：
   - "是否需要修复后再 release？"
   - "是否确认为误报，继续 release？"
3. 如果用户确认需要修复：
   - 暂停 release 流程
   - 加载 `postmortem` skill，分析并记录相关问题
   - 修复完成后从 Phase 1 重新开始
4. 如果用户确认继续：
   - 记录"用户已确认风险"
   - 进入 Phase 3

**重要**：此阶段是**建议性**门禁，不是强制阻断。最终决策权在用户手中。

---

## Phase 3: Update Version Files

Update both version files to maintain synchronization. **Skip this phase for first releases** where the version already matches.

### 3.1 Update pyproject.toml

File: `pyproject.toml` line 7

**Before**:
```toml
version = "0.1.0"
```

**After**:
```toml
version = "0.2.0"
```

Use the edit tool (preferred) or sed:
```bash
sed -i 's/^version = ".*"/version = "0.2.0"/' pyproject.toml
```

### 3.2 Update peeka/__init__.py

File: `peeka/__init__.py` line 2

**Before**:
```python
__version__ = "0.1.0"
```

**After**:
```python
__version__ = "0.2.0"
```

```bash
sed -i 's/^__version__ = ".*"/__version__ = "0.2.0"/' peeka/__init__.py
```

### 3.3 Verify Updates

```bash
# Verify both files updated correctly
pyproject_version=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
init_version=$(grep '^__version__ = ' peeka/__init__.py | cut -d'"' -f2)

if [ "$pyproject_version" = "0.2.0" ] && [ "$init_version" = "0.2.0" ]; then
    echo "✓ Both version files updated to 0.2.0"
else
    echo "Error: Version update failed"
    echo "  pyproject.toml:     $pyproject_version"
    echo "  peeka/__init__.py:  $init_version"
    exit 1
fi
```

---

## Phase 4: Commit, Tag, Push

Create a release commit (if version files changed), annotated tag, and push to trigger the automated workflow.

### 4.1 Stage and Commit Version Files (skip if first release with no changes)

```bash
git add pyproject.toml peeka/__init__.py
git commit -m "chore(release): bump version to 0.2.0"
```

**Commit Message Format**:
- Type: `chore` (release is a maintenance task)
- Scope: `release`
- Message: `bump version to X.Y.Z`

### 4.2 Create Annotated Tag

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
```

**Tag Format**:
- Prefix: `v` (mandatory — triggers GitHub Actions workflow)
- Version: `X.Y.Z` (semantic version)
- Annotation: `Release vX.Y.Z`

### 4.3 Draft GitHub Release Description

Before pushing the tag, draft the final GitHub Release body from the release commit range. This draft will replace the workflow's initial auto-generated notes in Phase 5.

**Collect commit context**:
```bash
previous_tag=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || true)
if [ -n "$previous_tag" ]; then
    release_range="$previous_tag..HEAD"
else
    release_range="HEAD"
fi

git log "$release_range" --pretty=format:"%h%x09%s" --no-merges
if [ -n "$previous_tag" ]; then
    git diff --stat "$previous_tag..HEAD"
else
    empty_tree=$(git hash-object -t tree /dev/null)
    git diff --stat "$empty_tree" HEAD
fi
```

**Summarization rules**:
- Summarize the release by user value and product impact, not by commit order.
- Group related commits into 3-5 concise bullets. Merge tiny style/test/docs commits into the nearest meaningful theme.
- Ignore `chore(release): ...` version bump commits.
- Mention fixes only when they affect reliability, usability, compatibility, diagnostics, or release confidence.
- Skip raw commit hashes and avoid a complete commit list in the primary release body.
- Keep the description clear enough to paste directly into a social post: short intro, compact bullets, no internal process noise.
- Do not include install or upgrade commands unless the user explicitly asks for them.
- Do not oversell. If a change is internal, phrase it as stability, compatibility, or maintainability only when that is true.

**Release body template**:
```markdown
Peeka vX.Y.Z is out.

This release <one-sentence summary of the main user-facing outcome>.

- <Highlight 1: concrete user value>
- <Highlight 2: concrete user value>
- <Highlight 3: fix, compatibility, or workflow improvement>
```

If the release has a larger surface area, add at most one extra bullet. Avoid separate "Features/Fixes/Docs" sections unless the release is too broad for a single compact list.

Save the draft outside the repository:
```bash
notes_file="/tmp/peeka-release-v$new_version.md"
# Write the curated Markdown body to $notes_file.
```

### 4.4 Push Commit and Tag

```bash
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)

# Prefer the configured remote first.
git push origin master --follow-tags
```

If the configured remote is SSH and fails because the SSH agent cannot sign, use GitHub CLI's HTTPS credentials:

```bash
gh auth setup-git
git push "https://github.com/${repo_full_name}.git" master --follow-tags
```

If push still fails because of permissions, stop the release flow and tell the user exactly what remains to push. Do not keep trying unrelated credentials or remotes.

**Verification**:
```bash
# Verify remote tag
gh api "repos/${repo_full_name}/git/ref/tags/v0.2.0" --jq .object.sha
```

### 4.5 Automated GitHub Actions Trigger

The tag push automatically triggers `.github/workflows/publish-pypi.yml` which:

1. **test** job: Runs `bash scripts/release_check.sh`
2. **publish** job: Builds wheel and publishes to PyPI via Trusted Publisher (OIDC)
3. **release** job: Creates the initial GitHub Release

The generated release body is only a placeholder. Phase 5 must replace it with the curated summary drafted in 4.3.

---

## Phase 5: Post-Release Verification

Verify the workflow succeeded and the package is available.

### 5.1 Check Workflow Status

```bash
# Watch the triggered workflow run in real time
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh run list --repo "$repo_full_name" --workflow=publish-pypi.yml --limit=1
gh run watch --repo "$repo_full_name"  # watches the latest run until completion
```

The workflow typically completes in 2-5 minutes.

### 5.2 Verify and Update GitHub Release Description

```bash
gh release view v0.2.0 --repo "$repo_full_name"
```

After the workflow creates the release, replace the generated commit-list body with the curated summary from Phase 4.3:

```bash
notes_file="/tmp/peeka-release-v$new_version.md"
gh release edit "v$new_version" --repo "$repo_full_name" --notes-file "$notes_file"
gh release view "v$new_version" --repo "$repo_full_name"
```

Verify the release body:
- Starts with a concise announcement line (`Peeka vX.Y.Z is out.` or equivalent).
- Contains one clear summary sentence and 3-5 user-facing bullets.
- Does not present the commit history as the main content.
- Can be copied directly into a short social-network post without editing.

If the workflow has not created the release yet, wait for the release job to finish and retry `gh release edit`.

### 5.3 Verify Package on PyPI

**Check package exists**:
```bash
curl -s https://pypi.org/pypi/peeka/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
# Expected output: 0.2.0
```

**Check all available versions**:
```bash
pip index versions peeka
```

**Test installation** (optional):
```bash
pip install peeka==0.2.0
python -c "import peeka; print(peeka.__version__)"
```

### 5.4 Success Confirmation

```
✓ Release v0.2.0 completed successfully

Summary:
  - Commit: abc1234 "chore(release): bump version to 0.2.0"
  - Tag: v0.2.0 (pushed to origin)
  - GitHub Release: https://github.com/<owner>/<repo>/releases/tag/v0.2.0
  - Release notes: curated summary applied
  - PyPI Package: https://pypi.org/project/peeka/0.2.0/
  - Workflow: https://github.com/<owner>/<repo>/actions/workflows/publish-pypi.yml
```

---

## Phase 6: Post-release Postmortem Analysis

Release 验证通过后，分析本次 release 范围内的所有 `fix:` 提交，为其生成或更新 postmortem 报告。

### 6.1 检测 Fix 提交

```bash
# 获取上一个 tag（即本次 release 之前的 tag）
previous_tag=$(git tag --sort=-v:refname | sed -n '2p')
# 如果只有一个 tag（首次 release），使用整个历史
if [ -z "$previous_tag" ]; then
    previous_tag=$(git rev-list --max-parents=0 HEAD)
fi

current_tag="v$new_version"

# 统计范围内 fix 提交数量
fix_count=$(git log $previous_tag..$current_tag --grep="^fix" --no-merges --oneline | wc -l)
```

### 6.2 决策分支

**无 fix 提交（`fix_count == 0`）**：

```
✓ Post-release postmortem check: no fix commits in $previous_tag..$current_tag — skipping
```

跳过此阶段，release 流程完成。

**存在 fix 提交（`fix_count > 0`）**：

```
ℹ Found N fix commit(s) in $previous_tag..$current_tag — invoking postmortem analysis
```

进入 6.3。

### 6.3 调用 Postmortem Skill

加载 `postmortem` skill，以上一个 tag 作为分析起点：

```
/postmortem $previous_tag
```

等价于执行 postmortem skill 的完整工作流（阶段 1-5）：

1. **发现并解析** `$previous_tag..$current_tag` 范围内的 fix 提交
2. **按话题分组**提交，匹配已有话题文件或创建新话题
3. **分析每个事故组块**（根因、严重级别、复现、教训）
4. **生成或追加** postmortem 报告到 `./postmortem/` 目录
5. **更新** `./postmortem/README.md` 汇总索引

### 6.4 提交 Postmortem 文件

如果 postmortem skill 生成了新文件或修改了已有文件：

```bash
# 检查是否有变更
status=$(git status --porcelain ./postmortem/)
if [ -n "$status" ]; then
    git add ./postmortem/
    git commit -m "docs(postmortem): add post-release analysis for v$new_version"
    repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
    git push "https://github.com/${repo_full_name}.git" master
fi
```

**提交消息格式**：
- Type: `docs`（postmortem 是文档）
- Scope: `postmortem`
- Message: `add post-release analysis for vX.Y.Z`

### 6.5 完成确认

```
✓ Post-release postmortem analysis completed

Summary:
  - Fix commits analyzed: N
  - Postmortem files created/updated: M
  - New topics: [list if any]
  - Updated topics: [list if any]
```

---

## Edge Cases

| Edge Case | Expected Behavior | Error Message |
|-----------|-------------------|---------------|
| First release (version already matches) | Skip version bump, tag and push only | `(First release — version files already at 0.1.0, skipping update)` |
| Version not greater than current | Error, abort | `Error: New version 0.1.0 must be greater than current 0.1.0` |
| Invalid version format (e.g., `1.2`) | Error, abort | `Error: Invalid version format. Use X.Y.Z or patch/minor/major` |
| Tag already exists locally or remotely | Error, abort | `Error: Tag v0.2.0 already exists` |
| Working directory has uncommitted changes | Error, abort | `Error: Working directory has uncommitted changes: M file.py` |
| Not on `master` branch | Error, abort | `Error: Must be on master branch (currently on develop)` |
| Version mismatch between files | Error, abort | `Error: Version mismatch between files` |
| Network error during push | Error, retry | `Error: Failed to push to origin. Check network connection.` |
| GitHub Actions workflow fails before PyPI publish | Fix, commit, move local tag, force-update the same tag | `git tag -f -a vX.Y.Z -m "Release vX.Y.Z"` then `git push --force ... vX.Y.Z` |
| GitHub Actions workflow fails after PyPI publish succeeds | Do not reuse the version; fix and bump a new patch version | `Error: vX.Y.Z already published to PyPI; release vX.Y.(Z+1)` |
| GitHub Release body is still a commit list | Replace with curated notes from Phase 4.3 | `gh release edit vX.Y.Z --notes-file /tmp/peeka-release-vX.Y.Z.md` |
| GitHub Release is not created yet | Wait for the release job, then retry notes update | `Warning: Release not found yet; retry after workflow completes` |
| PyPI publishing fails | Warning, check Actions tab | `Warning: PyPI publish failed. Check Trusted Publisher config.` |
| No postmortem directory exists | Phase 2 skips pattern check, Phase 6 creates directory | `(No existing postmortems — skipping pre-release check)` |
| Pre-release check finds HIGH risk | Present report, ask user to fix or continue | `⚠ HIGH risk: <details>. Fix before release?` |
| Pre-release check finds no risks | Pass through silently | `✓ Pre-release postmortem check passed` |
| No fix commits in release range | Phase 6 skips postmortem analysis | `✓ No fix commits — skipping postmortem analysis` |
| First release with no previous tag | Use initial commit as range start | `(First release — analyzing from initial commit)` |
| Postmortem skill generates changes | Auto-commit and push postmortem files | `docs(postmortem): add post-release analysis for vX.Y.Z` |

---

## Failure Recovery Procedure

If a release fails after pushing tags/commits, first identify the last successful stage in the workflow:

```bash
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh run view <run_id> --repo "$repo_full_name" --log-failed
```

### Case A: Failure happened before PyPI publish

Examples: unit tests fail, build fails before the `Publish to PyPI` step, or the workflow fails before artifacts are uploaded to PyPI.

In this case the version has not escaped to PyPI. It is acceptable to fix the issue and reuse the same version:

```bash
# 1. Fix the problem and commit it.
git add <files>
git commit -m "test(...): fix release gate"

# 2. Move the local tag to the new commit.
git tag -f -a v0.2.0 -m "Release v0.2.0"

# 3. Push master and force-update only this release tag.
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
git push "https://github.com/${repo_full_name}.git" master
git push --force "https://github.com/${repo_full_name}.git" v0.2.0
```

### Case B: PyPI publish succeeded

PyPI versions are immutable. If the package was published but a later step failed, do **not** move or reuse the tag/version for another package build.

Allowed actions:
- If only GitHub Release creation or notes replacement failed, fix the GitHub Release manually with `gh release create/edit`.
- If package contents are wrong, make a new fix commit and release the next patch version.

### Delete Tag Only When Aborting an Unpublished Release

Use this only when PyPI publish did not happen and you want to abandon the version entirely:

### 1. Delete Remote Tag
```bash
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
git push "https://github.com/${repo_full_name}.git" --delete v0.2.0
```

### 2. Delete Local Tag
```bash
git tag -d v0.2.0
```

### 3. Revert Commit
```bash
# If commit was pushed
git revert HEAD
git push "https://github.com/${repo_full_name}.git" master

# If commit not yet pushed
git reset --hard HEAD~1
```

### 4. Investigate Failure

Check the workflow logs at:
```
https://github.com/<owner>/<repo>/actions/workflows/publish-pypi.yml
```

Common issues:
- Build failures: Check pyproject.toml dependencies
- PyPI errors: Verify Trusted Publisher config at https://pypi.org/manage/account/publishing/
- Test failures: Run `bash scripts/release_check.sh` locally first

### 5. Fix and Retry
After fixing the issue, restart from Phase 1.

---

## Reference

### Version File Locations

| File | Line | Format | Example |
|------|------|--------|---------|
| `pyproject.toml` | 7 | TOML string | `version = "0.1.0"` |
| `peeka/__init__.py` | 2 | Python string | `__version__ = "0.1.0"` |

**Both files must always contain identical versions.**

### Git Commands Quick Reference

```bash
# Check status
git status --porcelain
git branch --show-current
git tag --list

# Version files
git add pyproject.toml peeka/__init__.py

# Commit and tag
git commit -m "chore(release): bump version to X.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"

# Push
repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
git push "https://github.com/${repo_full_name}.git" master --follow-tags

# Verify
gh api "repos/${repo_full_name}/git/ref/tags/vX.Y.Z" --jq .object.sha
```

### PyPI Verification Commands

```bash
# Check package exists
curl -s https://pypi.org/pypi/peeka/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"

# List all versions
pip index versions peeka

# Test install
pip install peeka==X.Y.Z

# Verify version
python -c "import peeka; print(peeka.__version__)"
```

---

## Complete Example Session

```bash
# === Phase 1: Validate ===
$ /release minor
✓ Version format valid: 0.2.0
✓ Version increases: 0.1.0 → 0.2.0
✓ Tag v0.2.0 does not exist
✓ Working directory clean
✓ On master branch
✓ Version files in sync
✓ bash scripts/release_check.sh passed

# === Phase 2: Pre-release Postmortem Check ===
Analyzing 23 commits from v0.1.0 to HEAD...
Loading postmortem knowledge base (16 topics, 73 incidents)...

⚠ RISK FINDINGS:

[MEDIUM] Commit def5678 "feat(tui): add parallel data loading in dashboard"
  → Touches high-risk module: peeka/tui/views/ (multiple postmortem topics)
  → Recommendation: 确保不同数据源使用独立客户端连接

✓ No HIGH risks found. 22 commits clear.
Proceeding with release.

# === Phase 3: Update Version Files ===
Updating pyproject.toml to 0.2.0...
Updating peeka/__init__.py to 0.2.0...
✓ Both version files updated to 0.2.0

# === Phase 4: Commit, Tag, Push ===
$ git add pyproject.toml peeka/__init__.py
$ git commit -m "chore(release): bump version to 0.2.0"
[master abc1234] chore(release): bump version to 0.2.0
 2 files changed, 2 insertions(+), 2 deletions(-)

$ git tag -a v0.2.0 -m "Release v0.2.0"

# Draft curated release notes
$ git log v0.1.0..HEAD --pretty=format:"%h%x09%s" --no-merges
$ git diff --stat v0.1.0..HEAD
$ notes_file="/tmp/peeka-release-v0.2.0.md"
# Agent writes a concise, user-facing summary to $notes_file:
# Peeka v0.2.0 is out.
#
# This release makes runtime diagnostics smoother and more reliable across TUI and attach workflows.
#
# - Adds ...
# - Improves ...
# - Fixes ...

$ repo_full_name=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
$ git push "https://github.com/${repo_full_name}.git" master --follow-tags
To https://github.com/peeka-project/peeka.git
   def5678..abc1234  master -> master
 * [new tag]         v0.2.0 -> v0.2.0

✓ Commit and tag pushed to origin
→ GitHub Actions workflow triggered automatically

# === Phase 5: Post-Release Verification ===
# Wait 2-5 minutes for workflow to complete
# Check: https://github.com/<owner>/<repo>/actions/workflows/publish-pypi.yml

$ gh release edit v0.2.0 --repo "$repo_full_name" --notes-file /tmp/peeka-release-v0.2.0.md
✓ GitHub Release description replaced with curated summary

$ curl -s https://pypi.org/pypi/peeka/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
0.2.0

✓ Release v0.2.0 completed successfully

Summary:
  - Commit: abc1234 "chore(release): bump version to 0.2.0"
  - Tag: v0.2.0 (pushed to origin)
  - GitHub Release: https://github.com/<owner>/<repo>/releases/tag/v0.2.0
  - Release notes: curated summary applied
  - PyPI Package: https://pypi.org/project/peeka/0.2.0/
  - Workflow: ✓ automated via GitHub Actions

# === Phase 6: Post-release Postmortem Analysis ===
Found 3 fix commit(s) in v0.1.0..v0.2.0 — invoking postmortem analysis...

Invoking: /postmortem v0.1.0
  - Analyzed 3 fix commits
  - Updated topic: 002-tui-memory-view.md (added incident #14)
  - Created topic: 017-dashboard-data-loading.md (1 incident)
  - Updated README.md index

$ git add ./postmortem/
$ git commit -m "docs(postmortem): add post-release analysis for v0.2.0"
$ git push "https://github.com/${repo_full_name}.git" master

✓ Post-release postmortem analysis completed
```

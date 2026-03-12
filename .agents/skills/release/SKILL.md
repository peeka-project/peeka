---
name: release
description: "Create a versioned release for peeka. Triggers: /release, version bump, publish to PyPI, create tag, github release, semver. Usage: /release <version|patch|minor|major>"
---

# Release Skill

Automate the complete release workflow for peeka: version updates, git commits, tags, and push. GitHub Actions handles PyPI publishing and GitHub Release creation automatically.

## Prerequisites

Before using this skill, ensure the following are configured:

1. **GitHub CLI authenticated**:
   ```bash
   gh auth status
   # Must show: Logged in to github.com as wwulfric
   ```

2. **PyPI Trusted Publisher** configured on pypi.org:
   - Add `wwulfric/peeka` repository as a trusted publisher
   - GitHub environment: `pypi` (uses OIDC token exchange, no secrets needed)

3. **Clean working directory**:
   - All changes committed
   - On `master` branch
   - No version drift between `pyproject.toml` and `peeka/__init__.py`

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

The release process consists of 4 phases executed sequentially. Each phase must succeed before proceeding to the next.

```
Phase 1: Parse & Validate Input
  ↓
Phase 2: Update Version Files
  ↓
Phase 3: Commit, Tag, Push
  ↓
Phase 4: Post-Release Verification
```

GitHub Actions automatically handles (triggered by tag push):
- Running tests
- Building and publishing to PyPI
- Creating GitHub Release with auto-generated notes

**Total Duration**: ~2-5 minutes (depends on GitHub Actions queue)

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
# Check if tag already exists on remote
gh release view v$new_version --repo wwulfric/peeka 2>/dev/null
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

---

## Phase 2: Update Version Files

Update both version files to maintain synchronization. **Skip this phase for first releases** where the version already matches.

### 2.1 Update pyproject.toml

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

### 2.2 Update peeka/__init__.py

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

### 2.3 Verify Updates

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

## Phase 3: Commit, Tag, Push

Create a release commit (if version files changed), annotated tag, and push to trigger the automated workflow.

### 3.1 Stage and Commit Version Files (skip if first release with no changes)

```bash
git add pyproject.toml peeka/__init__.py
git commit -m "chore(release): bump version to 0.2.0"
```

**Commit Message Format**:
- Type: `chore` (release is a maintenance task)
- Scope: `release`
- Message: `bump version to X.Y.Z`

### 3.2 Create Annotated Tag

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
```

**Tag Format**:
- Prefix: `v` (mandatory — triggers GitHub Actions workflow)
- Version: `X.Y.Z` (semantic version)
- Annotation: `Release vX.Y.Z`

### 3.3 Push Commit and Tag

```bash
# Push both in one command (atomic, safer)
git push origin master --follow-tags
```

**Verification**:
```bash
# Verify remote tag
git ls-remote --tags origin v0.2.0
# Expected output:
# abc123...  refs/tags/v0.2.0
```

### 3.4 Automated GitHub Actions Trigger

The tag push automatically triggers `.github/workflows/publish-pypi.yml` which:

1. **test** job: Runs unit tests
2. **publish** job: Builds wheel and publishes to PyPI via Trusted Publisher (OIDC)
3. **release** job: Creates GitHub Release with auto-generated release notes

**No manual intervention required** — everything is fully automated after the push.

---

## Phase 4: Post-Release Verification

Verify the workflow succeeded and the package is available.

### 4.1 Check Workflow Status

```bash
# Watch the triggered workflow run in real time
gh run list --workflow=publish-pypi.yml --limit=1
gh run watch  # watches the latest run until completion
```

The workflow typically completes in 2-5 minutes.

### 4.2 Verify GitHub Release

```bash
gh release view v0.2.0
```

### 4.3 Verify Package on PyPI

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

### 4.4 Success Confirmation

```
✓ Release v0.2.0 completed successfully

Summary:
  - Commit: abc1234 "chore(release): bump version to 0.2.0"
  - Tag: v0.2.0 (pushed to origin)
  - GitHub Release: https://github.com/wwulfric/peeka/releases/tag/v0.2.0
  - PyPI Package: https://pypi.org/project/peeka/0.2.0/
  - Workflow: https://github.com/wwulfric/peeka/actions/workflows/publish-pypi.yml
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
| GitHub Actions workflow fails | Warning, check Actions tab | `Warning: Check workflow at https://github.com/wwulfric/peeka/actions` |
| PyPI publishing fails | Warning, check Actions tab | `Warning: PyPI publish failed. Check Trusted Publisher config.` |

---

## Rollback Procedure

If a release fails after pushing tags/commits:

### 1. Delete Remote Tag
```bash
git push origin --delete v0.2.0
```

### 2. Delete Local Tag
```bash
git tag -d v0.2.0
```

### 3. Revert Commit
```bash
# If commit was pushed
git revert HEAD
git push origin master

# If commit not yet pushed
git reset --hard HEAD~1
```

### 4. Investigate Failure

Check the workflow logs at:
```
https://github.com/wwulfric/peeka/actions/workflows/publish-pypi.yml
```

Common issues:
- Build failures: Check pyproject.toml dependencies
- PyPI errors: Verify Trusted Publisher config at https://pypi.org/manage/account/publishing/
- Test failures: Run `pytest tests/ -v -m "not e2e and not container"` locally first

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

# Push (atomic)
git push origin master --follow-tags

# Verify
git ls-remote --tags origin vX.Y.Z
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

# === Phase 2: Update Version Files ===
Updating pyproject.toml to 0.2.0...
Updating peeka/__init__.py to 0.2.0...
✓ Both version files updated to 0.2.0

# === Phase 3: Commit, Tag, Push ===
$ git add pyproject.toml peeka/__init__.py
$ git commit -m "chore(release): bump version to 0.2.0"
[master abc1234] chore(release): bump version to 0.2.0
 2 files changed, 2 insertions(+), 2 deletions(-)

$ git tag -a v0.2.0 -m "Release v0.2.0"

$ git push origin master --follow-tags
To github.com:wwulfric/peeka.git
   def5678..abc1234  master -> master
 * [new tag]         v0.2.0 -> v0.2.0

✓ Commit and tag pushed to origin
→ GitHub Actions workflow triggered automatically

# === Phase 4: Post-Release Verification ===
# Wait 2-5 minutes for workflow to complete
# Check: https://github.com/wwulfric/peeka/actions/workflows/publish-pypi.yml

$ curl -s https://pypi.org/pypi/peeka/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
0.2.0

✓ Release v0.2.0 completed successfully

Summary:
  - Commit: abc1234 "chore(release): bump version to 0.2.0"
  - Tag: v0.2.0 (pushed to origin)
  - GitHub Release: https://github.com/wwulfric/peeka/releases/tag/v0.2.0
  - PyPI Package: https://pypi.org/project/peeka/0.2.0/
  - Workflow: ✓ automated via GitHub Actions
```

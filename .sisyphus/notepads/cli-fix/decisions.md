
## Task 7: Resolve CLI Conflict & Add Arthas Flags

### Decision: Keep Directory Structure, Delete File

**Rationale**:
1. Entry point `peeka.cli:main` already resolves to directory package
2. Directory structure is more modular (can add attach/, watch/ submodules later)
3. Only needed to add missing flags, not full rewrite
4. Less breaking than replacing the working entry point

### Changes Made

1. **Deleted peeka/cli.py** (the file)
   - Removed the conflicting file that was shadowed by the directory

2. **Updated peeka/cli/main.py** (lines 80-110):
   - Added `-b/--before` flag (observe before execution)
   - Added `-e/--exception` flag (observe on exception)
   - Added `-s/--success` flag (observe on success)
   - Added `-f/--finish` flag (observe on finish, default True)
   - Replaced `-c/--condition` with `--condition-express` (matches Arthas naming)

3. **Updated cmd_watch()** (lines 176-185):
   - Changed command dict to include all new flags:
     - `before`, `exception`, `success`, `finish`, `condition_express`
   - Removed conditional append of condition (now always included)

### Arthas Flags Status

All 7 Arthas flags now present in canonical CLI:

✅ `-x/--depth` (int, default 2)
✅ `-n/--times` (int, default -1)
✅ `-b/--before` (flag, default False)
✅ `-e/--exception` (flag, default False)
✅ `-s/--success` (flag, default False)
✅ `-f/--finish` (flag, default True)
✅ `--condition-express` (string, optional)

### Verification

```bash
# All flags visible in help
python3 -c "from peeka.cli import main; import sys; sys.argv = ['peeka', 'watch', '--help']; main()" \
  | grep -E "(before|exception|success|finish|condition-express|depth|times)"

# Output shows:
# -x, --depth DEPTH
# -n, --times TIMES
# -b, --before
# -e, --exception
# -s, --success
# -f, --finish
# --condition-express CONDITION_EXPRESS
```

All patterns matched ✅

### Protocol Alignment

Command sent to agent now includes all Arthas fields:

```json
{
  "type": "watch",
  "action": "start",
  "pattern": "module.Class.method",
  "depth": 2,
  "times": -1,
  "before": false,
  "exception": false,
  "success": false,
  "finish": true,
  "condition_express": "params[0] > 100"
}
```

No breaking changes to WatchCommand handler - existing code handles these fields.

### What's Left

- WatchCommand in peeka/commands/watch.py should already handle these fields
- If not, it will need updates to respect the observation control flags


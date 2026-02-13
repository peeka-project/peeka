# attach - Attach to Target Process

The `attach` command attaches Peeka to a running Python process, injecting the diagnostic agent.

## Usage

```bash
peeka-cli attach <pid>
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | integer | Yes | Process ID of target Python process |

## Examples

### Basic attachment

```bash
# Attach to process with PID 12345
peeka-cli attach 12345
```

### Check process ID first

```bash
# Find Python processes
ps aux | grep python

# Or use pgrep
pgrep -f "your_app.py"

# Then attach
peeka-cli attach <pid>
```

## Output

Success response:
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_12345.sock"}}
```

Error response:
```json
{"type":"error","command":"attach","error":"Permission denied"}
```

## Technical Details

### Python 3.14+
- Uses PEP 768 `sys.remote_exec()`
- Requires same UID or CAP_SYS_PTRACE

### Python 3.9-3.13
- Uses GDB + ptrace fallback
- Requires GDB and Python debug symbols (python3-dbg)
- Requires CAP_SYS_PTRACE or same UID
- ptrace_scope must be <= 1

## Troubleshooting

See [Troubleshooting Guide](troubleshooting.md#process-attachment-issues) for common issues and solutions.

## See Also

- [detach](detach.md) - Detach from process
- [watch](watch.md) - Watch function calls after attachment

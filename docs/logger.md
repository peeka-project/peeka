# logger - Dynamic Log Level Control

The `logger` command allows runtime adjustment of Python logger levels.

## Usage

```bash
peeka-cli logger [--action {list,get,set}] [options]
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--action` | string | Action to perform (list/get/set) |
| `--name` | string | Logger name (for get/set) |
| `--level` | string | Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

## Examples

```bash
# List all loggers
peeka-cli logger --action list

# Get logger level
peeka-cli logger --action get --name "myapp.module"

# Set logger level
peeka-cli logger --action set --name "myapp.module" --level DEBUG
```

## See Also

- [monitor](monitor.md) - Performance monitoring

# reset - Reset Instrumentation

The `reset` command removes instrumentation and restores original functions.

## Usage

```bash
peeka-cli reset [--pattern <pattern>]
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--pattern` | string | "*" | Pattern of functions to reset (* = all) |

## Examples

```bash
# Reset specific function
peeka-cli reset --pattern "module.func"

# Reset all instrumentation
peeka-cli reset
```

## See Also

- [watch](watch.md) - Watch function calls

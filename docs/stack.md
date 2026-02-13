# stack - Capture Call Stacks

The `stack` command captures the call stack when a function is invoked.

## Usage

```bash
peeka-cli stack <pattern> [options]
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | Required | Function pattern |
| `--times, -n` | integer | -1 | Number of captures |
| `--condition-express` | string | None | Filter condition |

## Examples

```bash
# Capture call stack
peeka-cli stack "module.critical_function"

# Limited captures
peeka-cli stack "module.func" --times 5
```

## See Also

- [trace](trace.md) - Trace call chains
- [watch](watch.md) - Observe function calls

# trace - Trace Function Call Chains

The `trace` command traces function call chains, showing the execution path and timing of nested function calls.

## Usage

```bash
peeka-cli trace <pattern> [options]
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | Required | Function pattern to trace |
| `--depth, -d` | integer | 3 | Maximum call depth to trace |
| `--times, -n` | integer | -1 | Number of traces (-1 = unlimited) |
| `--condition-express` | string | None | Filter condition |
| `--skip-builtin` | flag | true | Skip built-in functions |
| `--min-duration` | float | 0 | Minimum duration in ms |

## Examples

```bash
# Trace function with default depth
peeka-cli trace "module.Calculator.calculate"

# Trace with custom depth
peeka-cli trace "module.process" --depth 5

# Skip fast calls
peeka-cli trace "module.func" --min-duration 10
```

## Output Format

Tree structure showing call hierarchy:

```
`---[125.3ms] calculator.Calculator.calculate()
    +---[2.1ms] calculator.Calculator._validate()
    +---[98.2ms] calculator.Calculator._compute()
    |   `---[95.1ms] math.sqrt()
    `---[15.7ms] calculator.Logger.info()
```

## See Also

- [watch](watch.md) - Observe individual calls
- [stack](stack.md) - Capture call stacks

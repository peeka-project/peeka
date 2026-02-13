# monitor - Performance Monitoring

The `monitor` command provides periodic performance statistics for functions.

## Usage

```bash
peeka-cli monitor <pattern> [--interval SECONDS] [-c CYCLES]
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | Required | Function pattern to monitor |
| `--interval` | integer | 60 | Statistics interval in seconds |
| `-c, --cycles` | integer | -1 | Number of cycles (-1 = unlimited) |

## Examples

```bash
# Monitor with 5-second intervals
peeka-cli monitor "module.handler" --interval 5

# Limited monitoring
peeka-cli monitor "module.func" --interval 10 -c 6
```

## Output

Statistics include:
- Call count
- Success rate
- Average/min/max response time
- Throughput (calls/sec)

## See Also

- [watch](watch.md) - Detailed observation
- [trace](trace.md) - Call chain tracing

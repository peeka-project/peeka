# memory - Memory Analysis

The `memory` command provides memory analysis capabilities.

## Usage

```bash
peeka-cli memory [--action {overview,start,stop,top,dump,gc}] [options]
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--action` | string | Memory action to perform |
| `--limit` | integer | Number of results (for top) |

## Examples

```bash
# Memory overview
peeka-cli memory --action overview

# Top memory consumers
peeka-cli memory --action top --limit 20

# Trigger garbage collection
peeka-cli memory --action gc
```

## See Also

- [monitor](monitor.md) - Performance monitoring

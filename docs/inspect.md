# inspect - Runtime Object Inspection

The `inspect` command allows inspection of runtime objects and variables.

## Usage

```bash
peeka-cli inspect <expression>
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `expression` | string | Python expression to evaluate |

## Examples

```bash
# Inspect global variable
peeka-cli inspect "module.config"

# Inspect object attributes
peeka-cli inspect "app.settings.database"
```

## Security

Expressions are evaluated using simpleeval for safety. Complex or dangerous operations are blocked.

## See Also

- [search](search.md) - Search for classes and methods

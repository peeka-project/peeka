# search - Search Classes and Methods

The `search` commands allow searching for classes (`sc`) and methods (`sm`) in the target process.

## sc - Search Classes

Search for classes by name pattern.

### Usage

```bash
peeka-cli sc <pattern>
```

### Examples

```bash
# Search for Calculator class
peeka-cli sc "Calculator"

# Search with wildcard (if supported)
peeka-cli sc "*Calculator*"
```

## sm - Search Methods

Search for methods by name pattern.

### Usage

```bash
peeka-cli sm <pattern>
```

### Examples

```bash
# Search for all 'add' methods
peeka-cli sm "add"

# Search in specific class
peeka-cli sm "Calculator.add"
```

## Output Format

Results include:
- Fully qualified name
- Module location
- Method signature (for methods)

## See Also

- [watch](watch.md) - Watch found methods
- [inspect](inspect.md) - Inspect objects

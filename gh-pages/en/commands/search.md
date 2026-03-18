---
layout: default
title: Peeka Search Command Reference (sc / sm)
parent: Command Reference
nav_order: 9
permalink: /commands/search
---

# Peeka Search Command Reference (sc / sm)
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Command Overview

The `sc` (Search Class) and `sm` (Search Method) commands search for classes and methods in running Python processes, helping developers quickly understand code structure, discover available APIs, and locate target functions.

**Core Features**:
- **sc**: Search for classes in loaded modules
- **sm**: Search for methods within classes
- Support wildcard pattern matching (`*`, `?`)
- Display detailed information about classes/methods (file paths, docstrings, etc.)
- Result count limiting (avoid excessive output)
- Suitable for code exploration and dynamic analysis

**Typical Scenarios**:
- Explore unknown codebases (find available classes and methods)
- Search for specific functionality implementations (e.g., find all `*Handler` classes)
- Obtain function signatures (for use with `watch`, `stack`, etc.)
- Verify if modules are loaded
- Learn third-party library APIs

---

## TUI Usage

**Note**: The search command (sc/sm) has **no dedicated view in TUI**, but can be executed through the command input box:

- Press `:` in the TUI main interface to enter command mode
- Enter `sc <pattern>` or `sm <class_pattern>` to execute search
- Results are displayed in the command output area

**Quick Operations**:
- sc command: `: sc "myapp.*" -d --limit 20`
- sm command: `: sm "myapp.User" --method-pattern "get*"`

**Recommended Usage**: The search command is primarily used for code exploration. CLI mode is recommended for pipeline operations and result filtering.

**CLI Equivalent Commands**: All examples below use CLI commands for demonstration.

## Use Cases

### 1. Exploring Unknown Codebases

**Scenario**: Taking over a new project, need to quickly understand code structure.

```bash
# View all application classes (assuming module name is myapp)
peeka-cli sc "myapp.*"

# Output:
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.models.User
# myapp.models.Order
# myapp.utils.Helper
```

**Use**: Quickly understand which modules and classes the project has.

### 2. Finding Specific Functionality

**Scenario**: Need to find all handler classes.

```bash
# Search for all classes ending with Handler
peeka-cli sc "*Handler"

# Output:
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.api.PaymentHandler
```

### 3. Obtaining Method Signatures

**Scenario**: Want to use `watch` command to monitor a method but don't know the complete signature.

```bash
# Step 1: Search for class
peeka-cli sc "myapp.api.UserHandler"

# Step 2: Search for all methods of the class
peeka-cli sm "myapp.api.UserHandler.*"

# Output:
# get (self, user_id: int) -> dict
# create (self, **data) -> dict
# update (self, user_id: int, **data) -> bool
# delete (self, user_id: int) -> bool

# Step 3: Use watch to monitor
peeka-cli watch "myapp.api.UserHandler.get"
```

### 4. Verifying Module Loading

**Scenario**: Suspecting a module is not loaded, causing functionality unavailability.

```bash
# Search for classes in target module
peeka-cli sc "myapp.plugins.payment.*"

# If output is empty, module is not loaded
# If there's output, module is loaded
```

### 5. Learning Third-Party Library APIs

**Scenario**: Want to understand what classes and methods the `requests` library has.

```bash
# View all classes in requests module
peeka-cli sc "requests.*" -d

# View all methods of Session class
peeka-cli sm "requests.Session.*"

# Output:
# get (self, url, **kwargs) -> Response
# post (self, url, data=None, json=None, **kwargs) -> Response
# put (self, url, data=None, **kwargs) -> Response
# ...
```

---

## Command Format

### sc - Search Classes

```bash
peeka-cli sc [--pid PID | --name NAME] <pattern> [options]
```

**Required Parameters**:
- `--pid, -p`: Target process PID (choose one: `--pid` or `--name`)
- `--name`: Target process name (choose one: `--pid` or `--name`)
- `pattern`: Class pattern (supports wildcards)

**Optional Parameters**:
- `-d, --detail`: Display detailed information (file path, docstring)
- `--limit`: Result count limit (default 50)

### sm - Search Methods

```bash
peeka-cli sm [--pid PID | --name NAME] <class_pattern> [options]
```

**Required Parameters**:
- `--pid, -p`: Target process PID (choose one: `--pid` or `--name`)
- `--name`: Target process name (choose one: `--pid` or `--name`)
- `class_pattern`: Class pattern (supports wildcards)

**Optional Parameters**:
- `--method-pattern`: Method pattern (default `*`, matches all methods)
- `-d, --detail`: Display detailed information (module, docstring)

---

## sc Command - Search Classes

### Basic Usage

```bash
# Search for specific class
peeka-cli sc "myapp.User"

# Search for all classes in module
peeka-cli sc "myapp.models.*"

# Search for all classes ending with Handler
peeka-cli sc "*Handler"

# Display detailed information
peeka-cli sc "myapp.models.*" -d
```

### Output Fields

**Basic Mode** (without `-d`):
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"}
  ],
  "count": 2,
  "limit": 50
}
```

**Detailed Mode** (with `-d`):
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model class representing a system user."
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Pattern Examples

| Pattern | Match Examples | Description |
|---------|----------------|-------------|
| `json.*` | `json.JSONEncoder`, `json.JSONDecoder` | All classes in json module |
| `myapp.models.*` | `myapp.models.User`, `myapp.models.Order` | All classes in myapp.models module |
| `*Handler` | `UserHandler`, `OrderHandler` | All classes ending with Handler |
| `*Command` | `WatchCommand`, `StackCommand` | All classes ending with Command |
| `collections.Ordered*` | `collections.OrderedDict` | Classes starting with Ordered in collections module |

---

## sm Command - Search Methods

### Basic Usage

```bash
# Search for all methods of class
peeka-cli sm "myapp.User.*"

# Equivalent syntax (using --method-pattern)
peeka-cli sm "myapp.User" --method-pattern "*"

# Search for specific method
peeka-cli sm "myapp.User.get"

# Search for methods starting with get_
peeka-cli sm "myapp.User" --method-pattern "get_*"

# Display detailed information
peeka-cli sm "myapp.User.*" -d
```

### Output Fields

**Basic Mode** (without `-d`):
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    }
  ],
  "count": 2,
  "limit": 50
}
```

**Detailed Mode** (with `-d`):
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Pattern Combination Examples

| Class Pattern | Method Pattern | Match Examples |
|---------------|----------------|----------------|
| `myapp.User` | `*` | All methods of User class |
| `myapp.User` | `get*` | `get`, `get_by_id`, `get_all` |
| `myapp.User` | `*_by_id` | `get_by_id`, `delete_by_id` |
| `myapp.*Handler` | `handle` | handle method of all Handler classes |
| `json.JSONEncoder` | `encode*` | `encode`, `encode_object` |

---

## Pattern Syntax

### Supported Wildcards

| Wildcard | Description | Example |
|----------|-------------|---------|
| `*` | Matches any length of characters (including empty) | `myapp.*` matches `myapp.User`, `myapp.Order` |
| `?` | Matches single character | `User?` matches `User1`, `User2` |
| `[seq]` | Matches any character in seq | `User[12]` matches `User1`, `User2` |
| `[!seq]` | Matches any character not in seq | `User[!0]` matches `User1`, `User2` (not `User0`) |

### Pattern Types

#### 1. Fully Qualified Name

```bash
# Exact match
peeka-cli sc "myapp.models.User"
peeka-cli sm "myapp.models.User.get"
```

#### 2. Module-Level Wildcards

```bash
# All classes in module
peeka-cli sc "myapp.models.*"

# Multi-level wildcards
peeka-cli sc "myapp.*.User"  # User class in any submodule under myapp
```

#### 3. Class Name Wildcards

```bash
# Prefix match
peeka-cli sc "*Handler"       # All Handler classes
peeka-cli sc "myapp.*Handler" # All Handler classes under myapp

# Suffix match
peeka-cli sc "User*"          # User, UserHandler, UserModel

# Middle match
peeka-cli sc "*User*"         # UserHandler, AdminUser, User
```

#### 4. Method Name Wildcards

```bash
# Method patterns in sm command
peeka-cli sm "myapp.User" --method-pattern "get*"
peeka-cli sm "myapp.User" --method-pattern "*_by_id"
peeka-cli sm "myapp.User" --method-pattern "is_*"
```

---

## Output Format

### sc Command Output

**Basic Mode**:
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"},
    {"name": "myapp.api.UserHandler"}
  ],
  "count": 3,
  "limit": 50
}
```

**Detailed Mode** (`-d`):
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model representing a system user.\n\nAttributes:\n    id: User ID\n    username: Username"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### sm Command Output

**Basic Mode**:
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    },
    {
      "name": "update",
      "signature": "(self, user_id: int, **data) -> bool"
    }
  ],
  "count": 3,
  "limit": 50
}
```

**Detailed Mode** (`-d`):
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None if not found"
    }
  ],
  "count": 1,
  "limit": 50
}
```

---

## Usage Examples

### Example 1: Finding All Model Classes

```bash
peeka-cli sc "myapp.models.*" | jq -r '.classes[].name'
```

**Output**:
```
myapp.models.User
myapp.models.Order
myapp.models.Product
myapp.models.Payment
```

### Example 2: Finding All Handler Classes with Details

```bash
peeka-cli sc "*Handler" -d | jq .
```

**Output**:
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.api.UserHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles user-related API requests."
    },
    {
      "name": "myapp.api.OrderHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles order-related API requests."
    }
  ],
  "count": 2
}
```

### Example 3: Finding All Methods of a Class

```bash
peeka-cli sm "myapp.User.*" | jq -r '.methods[] | "\(.name)\(.signature)"'
```

**Output**:
```
get(self, user_id: int) -> dict
create(self, **data) -> dict
update(self, user_id: int, **data) -> bool
delete(self, user_id: int) -> bool
is_active(self) -> bool
```

### Example 4: Finding All Methods Starting with get_

```bash
peeka-cli sm "myapp.User" --method-pattern "get_*" | jq -r '.methods[].name'
```

**Output**:
```
get_by_id
get_by_username
get_all
get_active_users
```

### Example 5: Exploring Third-Party Libraries (requests)

```bash
# View classes in requests module
peeka-cli sc "requests.*" | jq -r '.classes[].name'

# Output:
# requests.Session
# requests.Response
# requests.Request
# requests.PreparedRequest

# View methods of Session class
peeka-cli sm "requests.Session" --method-pattern "*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# Output:
# get(self, url, **kwargs) -> Response
# post(self, url, data=None, json=None, **kwargs) -> Response
# ...
```

### Example 6: Combined with watch Command

**Scenario**: Find target method then use `watch` to monitor.

```bash
# Step 1: Search for all order processing methods
peeka-cli sm "myapp.Order" --method-pattern "*process*"

# Output:
# process_payment
# process_refund
# process_shipment

# Step 2: Select target method and monitor
peeka-cli watch "myapp.Order.process_payment" -n 10
```

---

## Complete Exploration Workflows

### Workflow 1: Exploring Unknown Codebase

**Goal**: Quickly understand project structure and main classes.

```bash
# Step 1: List all classes in application modules
peeka-cli sc "myapp.*" > classes.json

# Step 2: Group and count by module
jq -r '.classes[].name | split(".") | .[0:2] | join(".")' classes.json | \
  sort | uniq -c

# Output:
#   12 myapp.api
#   8 myapp.models
#   5 myapp.utils
#   3 myapp.services

# Step 3: View detailed classes for each module
peeka-cli sc "myapp.api.*" -d | \
  jq -r '.classes[] | "\(.name)\n  \(.docstring)\n"'
```

### Workflow 2: Locating Specific Functionality Implementation

**Goal**: Find all classes and methods implementing payment functionality.

```bash
# Step 1: Search for all payment-related classes
peeka-cli sc "*payment*" -d

# Step 2: After finding target class, view its methods
peeka-cli sm "myapp.payment.PaymentProcessor.*" -d

# Step 3: View details of specific method
peeka-cli sm "myapp.payment.PaymentProcessor.charge" -d | \
  jq -r '.methods[0].docstring'
```

### Workflow 3: Verifying Code Refactoring

**Goal**: After refactoring, verify old class is deleted and new class is loaded.

```bash
# Step 1: Search for old class (should not be found)
peeka-cli sc "myapp.OldUserHandler"
# Output: {"status":"success","classes":[],"count":0}

# Step 2: Search for new class (should be found)
peeka-cli sc "myapp.NewUserHandler" -d

# Step 3: Compare methods between old and new classes
peeka-cli sm "myapp.NewUserHandler.*" > new_methods.json
# Compare old_methods.json and new_methods.json
```

### Workflow 4: Learning Third-Party Library APIs

**Goal**: Learn core classes and methods of Flask framework.

```bash
# Step 1: View classes in Flask
peeka-cli sc "flask.*" | jq -r '.classes[].name'

# Output:
# flask.Flask
# flask.Blueprint
# flask.Request
# flask.Response

# Step 2: View all methods of Flask class
peeka-cli sm "flask.Flask.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# Step 3: View documentation of specific method
peeka-cli sm "flask.Flask.route" -d | \
  jq -r '.methods[0].docstring'
```

---

## Important Notes

### 1. Can Only Search Loaded Modules

**Important**: `sc` and `sm` commands can only search **already imported modules**.

```bash
# If myapp.plugin module is not imported, search will find nothing
peeka-cli sc "myapp.plugin.*"
# Output: {"classes": [], "count": 0}
```

**Solutions**:
- Trigger functionality to get module imported (e.g., access related API)
- Or check code to confirm module is indeed imported

### 2. Magic Methods Not Displayed by Default

**Default Behavior**: `sm` command does not display magic methods (`__init__`, `__str__`, etc.).

```bash
# Will not display __init__, __str__, __repr__, etc.
peeka-cli sm "myapp.User.*"
```

**Reason**: Magic methods are usually not business logic entry points, filtering reduces noise.

### 3. Result Count Limit

**Default Limit**: Maximum 50 results returned.

```bash
# If more than 50 matches, only first 50 returned
peeka-cli sc "*" --limit 50
```

**Adjusting Limit**:
```bash
# Increase limit to 200
peeka-cli sc "*" --limit 200
```

**Notes**:
- Excessive limit may cause too much output, performance degradation
- Recommend using more specific patterns instead of increasing limit

### 4. File Path May Be None

**Reason**: Some classes (e.g., built-in classes, C extensions) do not have corresponding Python files.

```bash
peeka-cli sc "builtins.dict" -d

# Output:
# {"name": "builtins.dict", "file": null, ...}
```

### 5. Signature May Be Unavailable

**Reason**: Some methods (e.g., C extensions, builtins) cannot get signature via `inspect.signature()`.

```bash
peeka-cli sm "builtins.dict.get"

# Output:
# {"name": "get", "signature": null}
```

### 6. Performance Impact

**Impact Degree**:
- `sc` and `sm` commands traverse `sys.modules`, may take several hundred milliseconds
- More results = longer output time
- Overall performance impact negligible (one-time operation)

**Recommendations**:
- Use specific patterns to reduce search scope
- Avoid frequent calls (e.g., in loops)

---

## FAQ

### Q1: Why can't I find a certain class?

**Possible Reasons**:
1. **Module not imported**: The module containing the class is not loaded into memory
2. **Pattern error**: Pattern does not match the fully qualified name of the class
3. **Results exceed limit**: Result count exceeds `--limit`

**Troubleshooting Methods**:
```bash
# Method 1: Check if module is imported
python3 -c "import sys; print('myapp.models' in sys.modules)"

# Method 2: Use more lenient pattern
peeka-cli sc "*User*"

# Method 3: Increase limit
peeka-cli sc "myapp.*" --limit 200
```

### Q2: How to search for all classes in all modules?

**Answer**: Use `*` wildcard.

```bash
peeka-cli sc "*" --limit 200
```

**Warning**:
- Result count may be very large (includes standard library and third-party libraries)
- Recommend using more specific patterns

### Q3: Why doesn't sm command display __init__ method?

**Reason**: Magic methods are filtered by default.

**If you need to view magic methods**:
- Current version does not support (may add `--show-magic` parameter in the future)
- Can use Python code to view:
  ```python
  import inspect
  print([m for m in dir(MyClass) if m.startswith('__')])
  ```

### Q4: How to match both class name and method name when searching methods?

**Method**: Use combination of `sm` command's two parameters.

```bash
# Search for handle method of all Handler classes
# Note: Need to know specific module name
peeka-cli sm "myapp.api.*Handler" --method-pattern "handle"
```

**Limitation**: `class_pattern` must include module name, cannot use `*Handler` alone.

### Q5: How to export search results to file?

**Method**: Use redirection or `jq`.

```bash
# Export all classes to file
peeka-cli sc "myapp.*" > classes.json

# Export class name list (plain text)
peeka-cli sc "myapp.*" | jq -r '.classes[].name' > class_names.txt

# Export method signature table
peeka-cli sm "myapp.User.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"' > user_methods.txt
```

### Q6: Can I search for standard library classes?

**Answer**: Yes, as long as the module is imported.

```bash
# Search for classes in json module
peeka-cli sc "json.*"

# Search for classes in collections module
peeka-cli sc "collections.*"

# Search for classes in logging module
peeka-cli sc "logging.*"
```

---

## Advanced Techniques

### 1. Generating Project API Documentation

**Scenario**: Automatically generate inventory of project classes and methods.

```bash
#!/bin/bash
# generate_api_doc.sh

PID=12345
OUTPUT="api_documentation.md"

echo "# API Documentation" > $OUTPUT
echo "" >> $OUTPUT

# Get all classes
classes=$(peeka-cli sc "myapp.*" | jq -r '.classes[].name')

for class in $classes; do
  echo "## $class" >> $OUTPUT
  echo "" >> $OUTPUT

  # Get class detailed information
  peeka-cli sc "$class" -d | \
    jq -r '.classes[0].docstring // "No description"' >> $OUTPUT
  echo "" >> $OUTPUT

  # Get all methods of class
  echo "### Methods" >> $OUTPUT
  echo "" >> $OUTPUT
  peeka-cli sm "$class.*" -d | \
    jq -r '.methods[] | "- `\(.name)\(.signature)`\n  \(.docstring // "No description")\n"' >> $OUTPUT
  echo "" >> $OUTPUT
done

echo "Documentation generated: $OUTPUT"
```

### 2. Code Refactoring Verification Script

**Scenario**: After refactoring, automatically verify if new and old class methods are consistent.

```bash
#!/bin/bash
# verify_refactor.sh

PID=12345
OLD_CLASS="myapp.OldUserHandler"
NEW_CLASS="myapp.NewUserHandler"

# Get old class methods
old_methods=$(peeka-cli sm "$OLD_CLASS.*" 2>/dev/null | \
  jq -r '.methods[].name' | sort)

# Get new class methods
new_methods=$(peeka-cli sm "$NEW_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# Compare
if [ "$old_methods" == "$new_methods" ]; then
  echo "✅ PASS: Method signatures match"
else
  echo "❌ FAIL: Method signatures differ"
  echo "Old methods:"
  echo "$old_methods"
  echo "New methods:"
  echo "$new_methods"
fi
```

### 3. Finding Unimplemented Abstract Methods

**Scenario**: Check which classes inherit from abstract class but don't implement all abstract methods.

```bash
#!/bin/bash
# find_abstract_violations.sh

PID=12345
ABSTRACT_CLASS="myapp.BaseHandler"

# Get all methods of abstract class
abstract_methods=$(peeka-cli sm "$ABSTRACT_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# Find all subclasses
subclasses=$(peeka-cli sc "*Handler" | \
  jq -r '.classes[].name' | grep -v "$ABSTRACT_CLASS")

for subclass in $subclasses; do
  # Get subclass methods
  impl_methods=$(peeka-cli sm "$subclass.*" | \
    jq -r '.methods[].name' | sort)

  # Check if all abstract methods are implemented
  missing=$(comm -23 <(echo "$abstract_methods") <(echo "$impl_methods"))

  if [ -n "$missing" ]; then
    echo "⚠️  $subclass missing methods:"
    echo "$missing"
  fi
done
```

### 4. Dynamic Module Import Exploration

**Scenario**: Target module not loaded, import first then search.

```bash
#!/bin/bash
# explore_module.sh

PID=12345
MODULE="myapp.plugins.experimental"

# Import module via Python code (requires Python 3.14+ or GDB method)
# Here assume module will be imported by triggering some functionality

# Wait for module to load (polling)
for i in {1..10}; do
  classes=$(peeka-cli sc "$MODULE.*" | jq -r '.count')
  if [ "$classes" -gt 0 ]; then
    echo "Module loaded successfully"
    peeka-cli sc "$MODULE.*" -d
    break
  fi
  echo "Waiting for module to load... ($i/10)"
  sleep 2
done
```

### 5. IDE Integration

**Scenario**: Generate auto-completion data usable by IDEs.

```bash
#!/bin/bash
# generate_autocomplete.sh

PID=12345

# Generate JSON format auto-completion data
peeka-cli sc "myapp.*" | \
  jq -r '.classes[] | .name' | \
  while read class; do
    peeka-cli sm "$class.*" | \
      jq -r ".methods[] | {class: \"$class\", method: .name, signature: .signature}"
  done | jq -s . > autocomplete_data.json
```

### 6. Monitoring Module Loading

**Scenario**: Real-time monitoring of which new modules/classes the application loads.

```bash
#!/bin/bash
# monitor_module_loading.sh

PID=12345
INTERVAL=5

# Save initial state
peeka-cli sc "*" | jq -r '.classes[].name' | sort > initial_classes.txt

while true; do
  sleep $INTERVAL

  # Get current class list
  peeka-cli sc "*" | jq -r '.classes[].name' | sort > current_classes.txt

  # Find newly added classes
  new_classes=$(comm -13 initial_classes.txt current_classes.txt)

  if [ -n "$new_classes" ]; then
    echo "[$(date)] New classes loaded:"
    echo "$new_classes"
  fi

  cp current_classes.txt initial_classes.txt
done
```

---


## Summary

The `sc` and `sm` commands are powerful tools for code exploration and dynamic analysis, especially suitable for:
- Exploring unknown codebases
- Finding specific functionality implementations
- Obtaining method signatures (for use with other commands)
- Verifying if modules are loaded
- Learning third-party library APIs

**Best Practices**:
- Use specific patterns to reduce search scope
- Combine with `-d` parameter for detailed information
- Use `jq` for powerful data processing
- Combine with `watch`, `stack`, and other commands
- Export search results for subsequent analysis

**Next Steps**:
- Learn about [`watch`](watch) command (observing function calls)
- Learn about [`stack`](stack) command (tracing call stacks)
- Learn about [`monitor`](monitor) command (performance monitoring)
- Refer to [AGENTS.md](../AGENTS) (developer guide)

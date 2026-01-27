# Testing Peeka Across Python Versions

This directory contains tests for validating Peeka compatibility across Python 3.9-3.14.

## Test Files

### `simple_compat_test.py` (Recommended)

Minimal compatibility test that works without pytest:

- ✅ No dependencies beyond stdlib
- ✅ Fast (< 1 second)
- ✅ Works on all Python versions
- Tests: Python version detection, module imports, security features

**Usage:**

```bash
python3 tests/simple_compat_test.py
```

### `test_compatibility.py` (pytest required)

Comprehensive compatibility tests:

- Requires pytest
- Tests attach mechanism, watch commands, condition filtering
- Includes process attach tests (may fail on restricted CI environments)

**Usage:**

```bash
pytest tests/test_compatibility.py -v
```

### `test_integration.py` (pytest required)

Full integration tests:

- Tests agent startup, client communication, streaming
- Requires pytest
- More comprehensive but slower

**Usage:**

```bash
pytest tests/test_integration.py -v
```

## GitHub Actions CI

The `.github/workflows/test-compatibility.yml` workflow:

- Tests Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
- Installs GDB and Python debug symbols for <3.14
- Configures ptrace permissions
- Runs simple compatibility tests (always)
- Runs pytest tests (if available)

## Local Testing

### Quick Test (No Setup)

```bash
cd /path/to/peeka
python3 tests/simple_compat_test.py
```

### Full Test (Requires Setup)

```bash
# Install dependencies
pip install pytest pytest-timeout

# Run all tests
pytest tests/ -v

# Run only compatibility tests
pytest tests/test_compatibility.py -v
```

## Testing on Specific Python Versions

Using pyenv:

```bash
# Install multiple Python versions
pyenv install 3.9.18
pyenv install 3.10.13
pyenv install 3.11.7
pyenv install 3.12.1
pyenv install 3.13.0
pyenv install 3.14.0

# Test each version
for version in 3.9.18 3.10.13 3.11.7 3.12.1 3.13.0 3.14.0; do
    echo "Testing Python $version"
    pyenv shell $version
    python tests/simple_compat_test.py
done
```

Using Docker:

```bash
for version in 3.9 3.10 3.11 3.12 3.13 3.14; do
    echo "Testing Python $version"
    docker run --rm -v $(pwd):/app python:$version python /app/tests/simple_compat_test.py
done
```

## Expected Results by Python Version

| Python Version | PEP 768 | GDB Fallback | Expected Result |
|----------------|---------|--------------|-----------------|
| 3.9            | ✗       | ✓ (if GDB)   | PASS            |
| 3.10           | ✗       | ✓ (if GDB)   | PASS            |
| 3.11           | ✗       | ✓ (if GDB)   | PASS            |
| 3.12           | ✗       | ✓ (if GDB)   | PASS            |
| 3.13           | ✗       | ✓ (if GDB)   | PASS            |
| 3.14+          | ✓       | N/A          | PASS            |

## Troubleshooting

### GDB not found (Python <3.14)

```bash
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# Arch
sudo pacman -S gdb
```

### ptrace permission denied

```bash
# Temporary (testing only)
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# Check current value
cat /proc/sys/kernel/yama/ptrace_scope
```

### Import errors

```bash
# Ensure you're in the project root
cd /path/to/peeka

# Or install in development mode
pip install -e .
```

## CI-Specific Notes

GitHub Actions Ubuntu runners:

- Default ptrace_scope: 1 (restricted)
- GDB pre-installed: yes (version 12+)
- Python debug symbols: must install manually
- Docker containers: need `--cap-add=SYS_PTRACE`

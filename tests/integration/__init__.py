"""Integration tests for peeka commands and features."""

import sys
import types
from contextlib import contextmanager


@contextmanager
def fake_gevent_monkey():
    """
    Standalone context manager for simulating gevent monkey patching.

    Creates fake gevent.monkey module in sys.modules with minimal API
    to make patch-status command detect it as "active" monkey patching.
    """
    # Create fake gevent module hierarchy
    fake_gevent = types.ModuleType("gevent")
    fake_monkey = types.ModuleType("gevent.monkey")

    # Simulate gevent.monkey.saved dict (tracks patched modules)
    fake_monkey.saved = {"socket": True, "threading": True}

    # Simulate gevent.monkey.is_module_patched() function
    fake_monkey.is_module_patched = lambda name: name in fake_monkey.saved

    fake_gevent.monkey = fake_monkey

    # Store originals (if any)
    original_gevent = sys.modules.get("gevent")
    original_gevent_monkey = sys.modules.get("gevent.monkey")

    try:
        # Install fake modules
        sys.modules["gevent"] = fake_gevent
        sys.modules["gevent.monkey"] = fake_monkey
        yield
    finally:
        # Restore originals
        if original_gevent is None:
            sys.modules.pop("gevent", None)
        else:
            sys.modules["gevent"] = original_gevent

        if original_gevent_monkey is None:
            sys.modules.pop("gevent.monkey", None)
        else:
            sys.modules["gevent.monkey"] = original_gevent_monkey

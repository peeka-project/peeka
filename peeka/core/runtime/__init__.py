"""
Runtime Primitive Layer (RPL) — Target-side only.

TARGET-SIDE ONLY. Do NOT import from peeka/cli/ or peeka/tui/.

This package provides eager-captured native runtime primitives that survive
gevent/eventlet monkey-patching. All primitives are captured at module import
time, before any gevent hub initialization.
"""

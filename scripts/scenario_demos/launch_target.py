"""Exec a Python script after allowing any same-user process to ptrace it.

Equivalent to ``python -u script.py`` but works with yama ptrace_scope=1
without sudo, so ``peeka-cli attach`` can reach it. The yama ptracer
exception survives ``exec``, so the target keeps a clean command line.
"""

import ctypes
import os
import sys

PR_SET_PTRACER = 0x59616D61
PR_SET_PTRACER_ANY = ctypes.c_ulong(-1 & 0xFFFFFFFFFFFFFFFF)

try:
    ctypes.CDLL(None).prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0)
except Exception:
    pass

os.execv(sys.executable, [sys.executable, "-u"] + sys.argv[1:])

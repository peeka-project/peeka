import sys
import sysconfig

from setuptools import Extension, setup

IS_LINUX = "linux" in sys.platform
IS_MAC = sys.platform == "darwin"

extra_compile_args = ["-fvisibility=hidden", "-std=c99", "-Wall"]
extra_link_args = []

if IS_LINUX:
    extra_link_args.append("-ldl")

# _inject.c does not include Python.h and only calls stable-ABI functions, so a
# single build works for every CPython >= 3.8. Build it as a cp38-abi3 wheel so
# one wheel per platform covers 3.8-3.14 (and the target interpreter that GDB/
# LLDB dlopen()s it into may differ from the interpreter running peeka).
# Free-threaded builds (3.13t/3.14t) have no limited API, so fall back to a
# version-specific build there.
py_limited_api = not sysconfig.get_config_var("Py_GIL_DISABLED")

inject_extension = Extension(
    name="peeka.core._inject",
    sources=["peeka/core/_inject.c"],
    language="c",
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    py_limited_api=py_limited_api,
)

setup(
    ext_modules=[inject_extension],
    options={"bdist_wheel": {"py_limited_api": "cp38"}} if py_limited_api else {},
)

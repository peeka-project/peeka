import sys
from setuptools import Extension, setup

IS_LINUX = "linux" in sys.platform
IS_MAC = sys.platform == "darwin"

extra_compile_args = ["-fvisibility=hidden", "-std=c99", "-Wall"]
extra_link_args = []

if IS_LINUX:
    extra_link_args.append("-ldl")

py_limited_api = sys.version_info[:2] >= (3, 9)

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
)

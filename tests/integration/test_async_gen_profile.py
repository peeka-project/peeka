"""Integration tests for async-gen and coroutine Execution Profile."""

import asyncio
import io
import json
import sys
from contextlib import redirect_stdout

import pytest

from peeka.core.injector import DecoratorInjector


class MockAgent:
    """Mock agent for injector tests."""

    def __init__(self):
        self.observer = None


class TestAsyncGenProfile:
    """Test async generator Execution Profile emission."""

    @pytest.mark.asyncio
    async def test_asyncgen_emits_profile(self):
        """Test async generator emits profile on normal completion."""
        async def stream_items():
            for i in range(3):
                yield i

        test_module = type(sys)("test_module_asyncgen")
        test_module.stream_items = stream_items
        sys.modules["test_module_asyncgen"] = test_module

        try:
            agent = MockAgent()
            injector = DecoratorInjector(agent)

            watch_id = injector.inject(
                "test_module_asyncgen.stream_items", {"depth": 2, "times": -1}
            )

            stdout_capture = io.StringIO()
            with redirect_stdout(stdout_capture):
                items = []
                async for item in test_module.stream_items():
                    items.append(item)

            assert items == [0, 1, 2]

            output_lines = stdout_capture.getvalue().strip().split("\n")
            profiles = []
            for line in output_lines:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if data.get("type") == "execution_profile":
                            profiles.append(data)
                    except json.JSONDecodeError:
                        pass

            assert len(profiles) == 1
            profile = profiles[0]
            assert profile["mode"] == "async_generator"
            assert profile["yields"] == 3
            assert profile["scheduler"] == "asyncio"
            assert profile["wall_cost"] > 0
            assert profile["termination"] == "exhausted"

            injector.uninject(watch_id)

        finally:
            del sys.modules["test_module_asyncgen"]

    @pytest.mark.asyncio
    async def test_aclose_emits_profile(self):
        """Test async generator emits profile on early aclose."""
        async def stream_items():
            for i in range(10):
                yield i

        test_module = type(sys)("test_module_asyncgen_aclose")
        test_module.stream_items = stream_items
        sys.modules["test_module_asyncgen_aclose"] = test_module

        try:
            agent = MockAgent()
            injector = DecoratorInjector(agent)

            watch_id = injector.inject(
                "test_module_asyncgen_aclose.stream_items", {"depth": 2, "times": -1}
            )

            stdout_capture = io.StringIO()
            with redirect_stdout(stdout_capture):
                gen = test_module.stream_items()
                items = []
                async for item in gen:
                    items.append(item)
                    if len(items) == 2:
                        await gen.aclose()
                        break

            assert items == [0, 1]

            output_lines = stdout_capture.getvalue().strip().split("\n")
            profiles = []
            for line in output_lines:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if data.get("type") == "execution_profile":
                            profiles.append(data)
                    except json.JSONDecodeError:
                        pass

            assert len(profiles) == 1
            profile = profiles[0]
            assert profile["mode"] == "async_generator"
            assert profile["yields"] == 2
            assert profile["termination"] == "closed"

            injector.uninject(watch_id)

        finally:
            del sys.modules["test_module_asyncgen_aclose"]


class TestCoroutineProfile:
    """Test coroutine Execution Profile emission."""

    @pytest.mark.asyncio
    async def test_coroutine_emits_profile(self):
        """Test coroutine emits profile on normal return."""
        async def simple_coro():
            await asyncio.sleep(0.001)
            return "done"

        test_module = type(sys)("test_module_coro")
        test_module.simple_coro = simple_coro
        sys.modules["test_module_coro"] = test_module

        try:
            agent = MockAgent()
            injector = DecoratorInjector(agent)

            watch_id = injector.inject(
                "test_module_coro.simple_coro", {"depth": 2, "times": -1}
            )

            stdout_capture = io.StringIO()
            with redirect_stdout(stdout_capture):
                result = await test_module.simple_coro()

            assert result == "done"

            output_lines = stdout_capture.getvalue().strip().split("\n")
            profiles = []
            for line in output_lines:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if data.get("type") == "execution_profile":
                            profiles.append(data)
                    except json.JSONDecodeError:
                        pass

            assert len(profiles) == 1
            profile = profiles[0]
            assert profile["mode"] == "coroutine"
            assert profile["scheduler"] == "asyncio"
            assert profile["yields"] is None
            assert profile["marker"] is None
            assert profile["wall_cost"] > 0
            assert profile["termination"] == "returned"

            injector.uninject(watch_id)

        finally:
            del sys.modules["test_module_coro"]

    @pytest.mark.asyncio
    async def test_shield_marker(self):
        """Test coroutine inside asyncio.shield gets shield marker."""
        async def shielded_coro():
            await asyncio.sleep(0.001)
            return "shielded"

        test_module = type(sys)("test_module_shield")
        test_module.shielded_coro = shielded_coro
        sys.modules["test_module_shield"] = test_module

        try:
            agent = MockAgent()
            injector = DecoratorInjector(agent)

            watch_id = injector.inject(
                "test_module_shield.shielded_coro", {"depth": 2, "times": -1}
            )

            stdout_capture = io.StringIO()
            with redirect_stdout(stdout_capture):
                result = await asyncio.shield(test_module.shielded_coro())

            assert result == "shielded"

            output_lines = stdout_capture.getvalue().strip().split("\n")
            profiles = []
            for line in output_lines:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if data.get("type") == "execution_profile":
                            profiles.append(data)
                    except json.JSONDecodeError:
                        pass

            assert len(profiles) == 1
            profile = profiles[0]
            assert profile["marker"] == "shield"

            injector.uninject(watch_id)

        finally:
            del sys.modules["test_module_shield"]

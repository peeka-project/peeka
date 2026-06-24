"""Tests for package import-time runtime policies."""

import os
import sys
import tempfile

import pytest

import peeka


class TestSudoBytecodePolicy:
    def test_sudo_import_redirects_bytecode_cache(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)

        peeka._configure_sudo_bytecode_policy(geteuid=lambda: 0)

        assert sys.pycache_prefix == os.path.join(
            tempfile.gettempdir(), "peeka-pycache-root"
        )

    def test_sudo_import_honors_custom_pycache_prefix(self, monkeypatch):
        custom_prefix = os.path.join(tempfile.gettempdir(), "custom-peeka-pycache")
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.setenv("PEEKA_SUDO_PYCACHE_PREFIX", custom_prefix)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)

        peeka._configure_sudo_bytecode_policy(geteuid=lambda: 0)

        assert sys.pycache_prefix == custom_prefix

    def test_non_sudo_import_preserves_pycache_prefix(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.delenv("SUDO_UID", raising=False)
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)

        peeka._configure_sudo_bytecode_policy(geteuid=lambda: 1000)

        assert sys.pycache_prefix is None

    def test_sudo_import_preserves_existing_pycache_prefix(self, monkeypatch):
        existing_prefix = os.path.join(tempfile.gettempdir(), "existing-pycache")
        monkeypatch.setattr(sys, "pycache_prefix", existing_prefix)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)

        peeka._configure_sudo_bytecode_policy(geteuid=lambda: 0)

        assert sys.pycache_prefix == existing_prefix

    def test_sudo_import_allows_redirect_disable(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.setenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", "1")

        peeka._configure_sudo_bytecode_policy(geteuid=lambda: 0)

        assert sys.pycache_prefix is None

    def test_platform_without_geteuid_skips_redirect(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.delenv("SUDO_UID", raising=False)
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)

        peeka._configure_sudo_bytecode_policy(geteuid=None)

        assert sys.pycache_prefix is None

    @pytest.fixture(autouse=True)
    def restore_pycache_prefix(self):
        original_prefix = sys.pycache_prefix
        yield
        sys.pycache_prefix = original_prefix

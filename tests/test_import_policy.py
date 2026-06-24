"""Tests for package import-time runtime policies."""

import importlib
import os
import sys
import tempfile

import peeka


class TestSudoBytecodePolicy:
    def test_sudo_import_redirects_bytecode_cache(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)
        monkeypatch.setattr(peeka.os, "geteuid", lambda: 0)

        importlib.reload(peeka)

        assert sys.pycache_prefix == os.path.join(
            tempfile.gettempdir(), "peeka-pycache-root"
        )

    def test_sudo_import_honors_custom_pycache_prefix(self, monkeypatch):
        custom_prefix = os.path.join(tempfile.gettempdir(), "custom-peeka-pycache")
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.setenv("PEEKA_SUDO_PYCACHE_PREFIX", custom_prefix)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)
        monkeypatch.setattr(peeka.os, "geteuid", lambda: 0)

        importlib.reload(peeka)

        assert sys.pycache_prefix == custom_prefix

    def test_non_sudo_import_preserves_pycache_prefix(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.delenv("SUDO_UID", raising=False)
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)
        monkeypatch.setattr(peeka.os, "geteuid", lambda: 1000)

        importlib.reload(peeka)

        assert sys.pycache_prefix is None

    def test_sudo_import_preserves_existing_pycache_prefix(self, monkeypatch):
        existing_prefix = os.path.join(tempfile.gettempdir(), "existing-pycache")
        monkeypatch.setattr(sys, "pycache_prefix", existing_prefix)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.delenv("PEEKA_SUDO_PYCACHE_PREFIX", raising=False)
        monkeypatch.delenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", raising=False)
        monkeypatch.setattr(peeka.os, "geteuid", lambda: 0)

        importlib.reload(peeka)

        assert sys.pycache_prefix == existing_prefix

    def test_sudo_import_allows_redirect_disable(self, monkeypatch):
        monkeypatch.setattr(sys, "pycache_prefix", None)
        monkeypatch.setenv("SUDO_UID", "501")
        monkeypatch.setenv("PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT", "1")
        monkeypatch.setattr(peeka.os, "geteuid", lambda: 0)

        importlib.reload(peeka)

        assert sys.pycache_prefix is None

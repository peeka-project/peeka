"""Regression tests for CLI bootstrap argv handling and attach script import root."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from peeka.core.attach import ProcessAttacher


class TestBootstrapArgvPreservation:
    """Verify bootstrap.py does not overwrite sys.argv mutations before Step 5."""

    @pytest.mark.parametrize(
        "source",
        [
            (
                "import sys\n"
                "sys.argv.pop()\n"
                "def f():\n"
                "    pass\n"
                "if __name__ == '__main__':\n"
                "    print(sys.argv[1:])\n"
            ),
            (
                "import sys\n"
                "sys.argv[1:] = ['mutated', sys.argv[-1]]\n"
                "def f():\n"
                "    pass\n"
                "print(sys.argv[1:])\n"
            ),
        ],
        ids=["pop-before-main-guard", "slice-assign-before-unguarded-tail"],
    )
    def test_bootstrap_preserves_early_sys_argv_mutations(
        self, tmp_path: Path, source: str
    ) -> None:
        script = tmp_path / "argv_mutating_script.py"
        script.write_text(source, encoding="utf-8")

        sid = uuid.uuid4().hex
        template = (
            Path(__file__).resolve().parents[1] / "peeka" / "core" / "bootstrap.py"
        ).read_text(encoding="utf-8")
        bootstrap = tmp_path / "bootstrap_run.py"
        bootstrap.write_text(
            template.replace("{{SESSION_ID}}", sid)
            .replace("{{SCRIPT_PATH}}", str(script))
            .replace("{{SCRIPT_DIR}}", str(tmp_path))
            .replace("{{SCRIPT_ARGS}}", repr(["arg1", "arg2"])),
            encoding="utf-8",
        )

        go_path = Path(f"/tmp/peeka_{sid}.go")
        go_path.write_text(str(os.getpid()), encoding="utf-8")
        try:
            expected = subprocess.run(
                [sys.executable, str(script), "arg1", "arg2"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            actual = subprocess.run(
                [sys.executable, str(bootstrap)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            assert expected.returncode == 0, expected.stderr
            assert actual.returncode == 0, actual.stderr
            assert actual.stdout == expected.stdout
        finally:
            go_path.unlink(missing_ok=True)
            Path(f"/tmp/peeka_{sid}.import-ready").unlink(missing_ok=True)


class TestAttachAgentScriptImportRoot:
    """Verify _create_agent_script() inserts the package parent directory into sys.path."""

    def test_generated_agent_script_imports_peeka_in_isolated_python(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attacher = ProcessAttacher(os.getpid())
        monkeypatch.setattr(attacher, "session_id", f"root-test-{uuid.uuid4().hex}")

        script_path = Path(attacher._create_agent_script("import peeka.core.agent"))
        try:
            expected_root = str(Path(__file__).resolve().parents[1])
            first_line = script_path.read_text(encoding="utf-8").splitlines()[0]
            assert repr(expected_root) in first_line

            # -BIS isolates from cwd, PYTHONPATH, user site, and site-packages .pth files.
            proc = subprocess.run(
                [sys.executable, "-BIS", str(script_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            assert proc.returncode == 0, proc.stderr
        finally:
            script_path.unlink(missing_ok=True)

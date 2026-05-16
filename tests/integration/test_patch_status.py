"""Integration tests for patch-status command."""



from peeka.commands.patch_status import PatchStatusCommand
from peeka.commands.patch_status_schema import validate
from tests.integration import fake_gevent_monkey


class TestPatchStatusCommand:
    """Test patch-status command introspection."""

    def test_clean_process(self):
        """Test patch-status on clean process (no gevent/eventlet)."""
        cmd = PatchStatusCommand()
        result = cmd.execute({})

        assert result["status"] == "success"
        data = result["data"]

        errors = validate(data)
        assert errors == [], f"Schema validation failed: {errors}"

        assert data["monkey_patch"]["gevent"] == "not_imported"
        assert data["monkey_patch"]["eventlet"] == "not_imported"

        assert data["rpl_integrity"]["ok"] is True
        assert data["rpl_integrity"]["status"] == "ok"

    def test_reports_fake_monkey(self):
        """Test patch-status detects fake monkey patching from chaos fixture."""
        with fake_gevent_monkey():
            cmd = PatchStatusCommand()
            result = cmd.execute({})

            assert result["status"] == "success"
            data = result["data"]

            assert isinstance(data["monkey_patch"]["gevent"], dict)
            assert data["monkey_patch"]["gevent"]["status"] == "active"
            assert "socket" in data["monkey_patch"]["gevent"]["patched_modules"]

    def test_rpl_integrity_after_chaos(self):
        """Test RPL integrity remains OK under fake monkey patching."""
        with fake_gevent_monkey():
            cmd = PatchStatusCommand()
            result = cmd.execute({})

            assert result["status"] == "success"
            data = result["data"]

            assert data["rpl_integrity"]["ok"] is True
            assert data["rpl_integrity"]["status"] == "ok"

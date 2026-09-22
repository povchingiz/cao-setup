import json
from unittest.mock import patch, MagicMock
from run.cao_auto import AutonomousRunner

def test_audit_gate_pass(tmp_path):
    tasks = [{"id": "t1", "status": "done", "depends_on": []}]
    session_dir = tmp_path / "cao_session" / "session_001"
    session_dir.mkdir(parents=True)
    tasks_file = session_dir / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=True)
    passed, notes = runner._run_audit_gate(tasks)
    assert passed is True
    assert tasks[0]["qa"]["verdict"] == "pass"

def test_audit_gate_failure(tmp_path):
    tasks = [{"id": "t1", "status": "done", "depends_on": []}]
    session_dir = tmp_path / "cao_session" / "session_001"
    session_dir.mkdir(parents=True)
    tasks_file = session_dir / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    # Create dummy pyproject.toml in root to trigger test command
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=False)
    with patch("subprocess.run") as mock_sub:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "FAILED test_something"
        mock_sub.return_value = mock_res

        passed, notes = runner._run_audit_gate(tasks)
        assert passed is False
        assert tasks[0]["qa"]["verdict"] == "block"
        assert "FAILED test_something" in tasks[0]["qa"]["notes"]

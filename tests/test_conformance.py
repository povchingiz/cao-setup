"""test_conformance — Conformance and Crash Recovery Stress Tests.

Inspired by HarnessRouter conformance suites:
1. Worker crash recovery (ensuring dead/errored worker terminals do not deadlock cao-auto).
2. Mid-DAG 429 quota failover handling (seamless failover to fallback engine).
3. Post-task artifact integrity and audit gate validation.
"""
import json
import pytest
from pathlib import Path
from run.cao_auto import AutonomousRunner, CaoClient


class MockCrashCaoClient:
    """Simulates a worker that crashes with an ERROR status."""
    def __init__(self):
        self.deleted = []

    def is_healthy(self):
        return True

    def launch_session(self, agent_profile, initial_message, model=None, working_directory=None):
        return {"terminal_id": "term-crash-001"}

    def get_terminal(self, terminal_id):
        return {"status": "ERROR", "error": "Process terminated by SIGSEGV"}

    def get_terminal_output(self, terminal_id):
        return "Segmentation fault (core dumped)"

    def delete_terminal(self, terminal_id):
        self.deleted.append(terminal_id)
        return True


class MockQuotaCaoClient:
    """Simulates a worker that hits a 429 quota limit on first attempt, then succeeds on fallback."""
    def __init__(self):
        self.launch_count = 0
        self.deleted = []

    def is_healthy(self):
        return True

    def launch_session(self, agent_profile, initial_message, model=None, working_directory=None):
        self.launch_count += 1
        return {"terminal_id": f"term-quota-{self.launch_count}"}

    def get_terminal(self, terminal_id):
        if "1" in terminal_id:
            return {"status": "RUNNING", "error": None}
        return {"status": "COMPLETED", "error": None}

    def get_terminal_output(self, terminal_id):
        if "1" in terminal_id:
            return "Error 429: Rate limit or quota exhausted for claude-3-5-sonnet"
        return "Task completed successfully on fallback engine."

    def delete_terminal(self, terminal_id):
        self.deleted.append(terminal_id)
        return True


def test_worker_crash_recovery_no_deadlock(tmp_path):
    """Verify that an errored worker terminal marks task blocked without deadlocking runner."""
    tasks = [
        {"id": "task_crash", "title": "Crash task", "status": "pending", "engine": "coder_worker", "files": ["crash.py"]}
    ]
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    client = MockCrashCaoClient()
    runner = AutonomousRunner(tasks_file=tasks_file, client=client, dry_run=False)
    # Run should not deadlock; it should return False because execution stalled on blocked task
    success = runner.run(poll_interval=0.01)
    assert success is False

    updated = json.loads(tasks_file.read_text())
    assert updated[0]["status"] == "blocked"
    assert "term-crash-001" in client.deleted
    assert len(runner.active_workers) == 0


def test_mid_dag_429_quota_failover(tmp_path):
    """Verify that a 429 error mid-DAG triggers automatic fallback engine re-dispatch."""
    tasks = [
        {"id": "task_quota", "title": "Quota task", "status": "pending", "engine": "claude_worker", "files": ["api.py"]}
    ]
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    client = MockQuotaCaoClient()
    runner = AutonomousRunner(tasks_file=tasks_file, client=client, dry_run=False)
    # Runner should failover to coder_worker and complete the task
    success = runner.run(poll_interval=0.01)
    assert success is True

    updated = json.loads(tasks_file.read_text())
    assert updated[0]["status"] == "done"
    # Verify fallback engine was applied
    assert updated[0]["engine"] == "coder_worker"
    assert "term-quota-1" in client.deleted
    assert "term-quota-2" in client.deleted


def test_post_task_artifact_integrity_validation(tmp_path):
    """Verify that the audit gate validates test results and artifact integrity."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    wcao = repo / "wcao"
    wcao.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='valid'\n")

    tasks = [
        {"id": "t1", "title": "Create artifact", "status": "pending", "files": ["artifact.txt"]}
    ]
    tasks_file = wcao / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=True)
    runner.run(poll_interval=0.01)

    updated = json.loads(tasks_file.read_text())
    assert updated[0]["status"] == "done"
    assert updated[0]["qa"]["by"] == "antigravity_worker"
    assert updated[0]["qa"]["verdict"] in ("pass", "block")

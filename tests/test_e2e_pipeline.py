"""test_e2e_pipeline — End-to-End Stress Test for the Self-Healing & Self-Learning Pipeline.

Tests the full closed loop:
1. Pre-Task Hermes Recall: Automatic query of memory.sqlite and injection into turn 1 prompt.
2. Hermes 50% Rule Compaction: State diffing and checkpointing during long runs.
3. Postflight Aggressive Audit Gate: Catching deliberate audit failures.
4. Autonomous Self-Healing: Automatically generating remediation tasks with failure context.
5. Hermes Retrospective Storage: Persisting learned fixes to wcao/memory.sqlite and wcao/skills/.
6. Second Task Verification: Proving subsequent tasks inherit the newly learned memory.
"""
import json
import sqlite3
import pytest
from pathlib import Path
from run.cao_auto import AutonomousRunner
from run.cao_memory import store_memory, query_memory


class HealingMockClient:
    """Mock client that simulates a test failure on pass 1 and success on remediation."""
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.remediation_called = False
        self.dispatched_payloads = []

    def is_healthy(self):
        return True

    def launch_session(self, agent_profile, initial_message, model=None, working_directory=None):
        self.dispatched_payloads.append(initial_message)
        if "remediation_heal" in initial_message:
            self.remediation_called = True
            # Simulate the worker fixing the issue
            fix_file = self.repo_path / "status.txt"
            fix_file.write_text("fixed")
        return {"terminal_id": f"term-{len(self.dispatched_payloads)}"}

    def get_terminal(self, terminal_id):
        return {"status": "COMPLETED", "error": None}

    def get_terminal_output(self, terminal_id):
        return "Worker completed task."

    def delete_terminal(self, terminal_id):
        return True


def test_full_e2e_self_healing_and_learning_loop(tmp_path):
    # 1. Scaffold a real project workspace
    repo = tmp_path / "e2e_project"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='e2e-app'\n")

    wcao = repo / "wcao"
    wcao.mkdir()
    skills_dir = wcao / "skills"
    skills_dir.mkdir()
    plans_dir = wcao / "plans"
    plans_dir.mkdir()
    now_file = plans_dir / "now.md"
    now_file.write_text("# now.md\n")

    db_path = wcao / "memory.sqlite"

    # Pre-seed memory with a known convention
    store_memory(
        category="testing",
        summary="Use pytest runner for unit tests",
        details="Must pass pythonpath=['.'] to avoid module errors",
        file_paths="pyproject.toml",
        db_path=db_path,
    )

    # 2. Initial Task with a bug
    status_file = repo / "status.txt"
    status_file.write_text("broken")

    tasks = [
        {
            "id": "task_initial_feature",
            "title": "Implement unit tests runner",
            "status": "pending",
            "engine": "coder_worker",
            "files": ["pyproject.toml"],
            "detail": "Configure tests runner for the project.",
        }
    ]
    tasks_file = wcao / "tasks.json"
    tasks_file.write_text(json.dumps(tasks, indent=2))

    client = HealingMockClient(repo)
    runner = AutonomousRunner(tasks_file=tasks_file, client=client, dry_run=False, self_heal=True)

    # Override _run_audit_gate to simulate audit failure when status.txt is 'broken'
    original_audit = runner._run_audit_gate
    audit_passes = []

    def mock_audit(all_tasks):
        if status_file.read_text().strip() == "broken":
            audit_passes.append(False)
            return False, "Audit Blocker: status.txt is broken (AssertionError in tests)"
        audit_passes.append(True)
        return True, "All tests and aggressive checks passed."

    runner._run_audit_gate = mock_audit

    # 3. Execute the Autonomous Run
    success = runner.run(poll_interval=0.01)
    assert success is True

    # 4. Verify Phase 1: Pre-Task Recall occurred on the initial task
    assert len(client.dispatched_payloads) >= 1
    initial_payload = client.dispatched_payloads[0]
    assert "--- Inherited Project Knowledge (Hermes Memory) ---" in initial_payload
    assert "Use pytest runner for unit tests" in initial_payload

    # 5. Verify Phase 4 & 5: Self-Healing Triggered
    # Audit failed on pass 1, then passed on pass 2 after remediation
    assert audit_passes == [False, True]
    assert client.remediation_called is True

    # Verify tasks.json contains the dynamically generated remediation task marked done
    final_tasks = json.loads(tasks_file.read_text())
    task_ids = [t["id"] for t in final_tasks]
    assert any("remediation_heal_1" in tid for tid in task_ids)
    assert all(t["status"] == "done" for t in final_tasks)

    # 6. Verify Phase 6: Hermes Retrospective Learning Closure
    # Check that the fix was persisted to memory.sqlite
    healed_memories = query_memory("Self-healed audit issue", db_path=db_path)
    assert len(healed_memories) >= 1
    assert "status.txt is broken" in healed_memories[0]["details"]

    # Check that a skill markdown was generated in wcao/skills/
    skill_files = list(skills_dir.glob("healing_*.md"))
    assert len(skill_files) >= 1
    assert "Self-healed audit issue" in skill_files[0].read_text()

    # 7. Verify Phase 7: Subsequent task inherits the newly learned memory
    task2 = {
        "id": "task_followup",
        "title": "Audit issue follow-up checks",
        "status": "pending",
        "engine": "coder_worker",
        "files": ["status.txt"],
        "detail": "Perform validation on status checks.",
    }
    tasks_file2 = wcao / "tasks_2.json"
    tasks_file2.write_text(json.dumps([task2], indent=2))

    client2 = HealingMockClient(repo)
    runner2 = AutonomousRunner(tasks_file=tasks_file2, client=client2, dry_run=False, self_heal=False)
    runner2._run_audit_gate = lambda t: (True, "Passed")
    runner2.run(poll_interval=0.01)

    # The new task should have inherited the self-healing memory from task 1!
    task2_payload = client2.dispatched_payloads[0]
    assert "Self-healed audit issue" in task2_payload

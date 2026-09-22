import pytest
from run.cao_auto import DagScheduler

def test_dag_scheduler_ready_tasks():
    tasks = [
        {"id": "t1", "status": "pending", "depends_on": [], "files": ["a.py"]},
        {"id": "t2", "status": "pending", "depends_on": ["t1"], "files": ["b.py"]},
        {"id": "t3", "status": "pending", "depends_on": [], "files": ["a.py"]},
    ]
    scheduler = DagScheduler(tasks)
    # When no files are running, t1 is ready. t2 waits for t1. t3 collides with t1 on a.py
    ready = scheduler.get_ready_tasks(running_files=set())
    assert [t["id"] for t in ready] == ["t1"]

def test_dag_scheduler_unlocks_downstream_after_done():
    tasks = [
        {"id": "t1", "status": "done", "depends_on": [], "files": ["a.py"]},
        {"id": "t2", "status": "pending", "depends_on": ["t1"], "files": ["b.py"]},
    ]
    scheduler = DagScheduler(tasks)
    ready = scheduler.get_ready_tasks(running_files=set())
    assert [t["id"] for t in ready] == ["t2"]

def test_dag_scheduler_disjoint_file_locks():
    tasks = [
        {"id": "t1", "status": "pending", "depends_on": [], "files": ["a.py"]},
        {"id": "t2", "status": "pending", "depends_on": [], "files": ["b.py"]},
    ]
    # If a.py is already being modified by an active worker, t1 cannot run yet
    scheduler = DagScheduler(tasks)
    ready = scheduler.get_ready_tasks(running_files={"a.py"})
    assert [t["id"] for t in ready] == ["t2"]

def test_dag_scheduler_is_complete():
    tasks_incomplete = [
        {"id": "t1", "status": "done", "depends_on": []},
        {"id": "t2", "status": "running", "depends_on": []},
    ]
    assert DagScheduler(tasks_incomplete).is_complete() is False

    tasks_complete = [
        {"id": "t1", "status": "done", "depends_on": []},
        {"id": "t2", "status": "done", "depends_on": []},
    ]
    assert DagScheduler(tasks_complete).is_complete() is True

def test_autonomous_runner_dry_run(tmp_path):
    import json
    from run.cao_auto import AutonomousRunner
    tasks = [
        {"id": "t1", "title": "Build DB", "status": "pending", "depends_on": [], "files": ["db.py"]},
        {"id": "t2", "title": "Build API", "status": "pending", "depends_on": ["t1"], "files": ["api.py"]},
    ]
    session_dir = tmp_path / "cao_session" / "session_001"
    session_dir.mkdir(parents=True)
    tasks_file = session_dir / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=True)
    success = runner.run(poll_interval=0.1)
    assert success is True

    # Verify tasks are marked done with QA verdicts
    updated = json.loads(tasks_file.read_text())
    assert all(t["status"] == "done" for t in updated)
    assert all(t.get("qa") is not None for t in updated)

def test_find_repo_root(tmp_path):
    from run.cao_auto import find_repo_root
    repo = tmp_path / "my_project"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='test'\n")
    wcao = repo / "wcao"
    wcao.mkdir()
    sub = wcao / "sessions" / "session_001"
    sub.mkdir(parents=True)

    assert find_repo_root(wcao) == repo
    assert find_repo_root(sub) == repo

def test_autonomous_runner_wcao_repo_root(tmp_path):
    import json
    from run.cao_auto import AutonomousRunner
    repo = tmp_path / "sample_repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    wcao = repo / "wcao"
    wcao.mkdir()
    tasks_file = wcao / "tasks.json"
    tasks_file.write_text("[]")

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=True)
    assert runner.repo_root == repo

def test_autonomous_runner_compactor_integration(tmp_path):
    import json
    from run.cao_auto import AutonomousRunner
    repo = tmp_path / "compactor_repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    wcao = repo / "wcao"
    wcao.mkdir()
    plans = wcao / "plans"
    plans.mkdir()
    now_file = plans / "now.md"
    now_file.write_text("# now.md\n")

    tasks = [{"id": "t1", "title": "Quick task", "status": "pending", "depends_on": []}]
    tasks_file = wcao / "tasks.json"
    tasks_file.write_text(json.dumps(tasks))

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=True)
    # Set turn_threshold=1 so it triggers immediately
    runner.compactor.turn_threshold = 1
    runner.run(poll_interval=0.01)

    assert "## Context Compaction Checkpoint" in now_file.read_text()

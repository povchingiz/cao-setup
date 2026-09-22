"""Unit tests for run/cao_plan.py — Goal Decomposer and DAG Planner."""
from pathlib import Path
from unittest.mock import MagicMock

from run.cao_limits import ClaudeLimits, WindowInfo
from run.cao_plan import (
    decompose_goal,
    extract_goal_from_now_md,
    save_plan,
    validate_dag,
)
from run.cao_token_master import TokenMaster


def test_validate_dag_valid():
    tasks = [
        {"id": "t1", "depends_on": []},
        {"id": "t2", "depends_on": ["t1"]},
        {"id": "t3", "depends_on": ["t1", "t2"]},
    ]
    valid, msg = validate_dag(tasks)
    assert valid is True
    assert "acyclic" in msg


def test_validate_dag_cycle():
    tasks = [
        {"id": "t1", "depends_on": ["t2"]},
        {"id": "t2", "depends_on": ["t1"]},
    ]
    valid, msg = validate_dag(tasks)
    assert valid is False
    assert "Cycle detected" in msg


def test_validate_dag_missing_dep():
    tasks = [
        {"id": "t1", "depends_on": ["non_existent_task"]},
    ]
    valid, msg = validate_dag(tasks)
    assert valid is False
    assert "depends on non-existent task" in msg


def test_extract_goal_from_now_md(tmp_path: Path):
    now_file = tmp_path / "now.md"
    now_file.write_text("# now.md\n\n## North Star Goal\nBuild a decentralized cache layer\n\n## Tasks\n")
    goal = extract_goal_from_now_md(now_file)
    assert goal == "Build a decentralized cache layer"


def test_decompose_goal(tmp_path: Path):
    # Mock TokenMaster with normal Claude quota
    tm = TokenMaster()
    tm.get_claude_quota_state = MagicMock(return_value=ClaudeLimits(
        five_hour=WindowInfo(utilization=0.20),
    ))

    tasks = decompose_goal("Build JWT auth service", repo_root=tmp_path, token_master=tm)
    assert len(tasks) == 4
    # Task 1: Architecture
    assert tasks[0]["id"].endswith("_arch")
    assert tasks[0]["engine"] == "claude_worker"
    # Task 2: Implementation (depends on Task 1)
    assert tasks[1]["id"].endswith("_impl")
    assert tasks[1]["depends_on"] == [tasks[0]["id"]]
    assert tasks[1]["engine"] == "coder_worker"
    # Task 3: Tests (depends on Task 2)
    assert tasks[2]["id"].endswith("_tests")
    assert tasks[2]["depends_on"] == [tasks[1]["id"]]
    # Task 4: Verification (depends on Task 3)
    assert tasks[3]["id"].endswith("_verify")
    assert tasks[3]["depends_on"] == [tasks[2]["id"]]

    valid, _ = validate_dag(tasks)
    assert valid is True


def test_decompose_goal_proactive_swap(tmp_path: Path):
    # Mock TokenMaster with high Claude quota -> swaps arch to hermes_worker
    tm = TokenMaster()
    tm.get_claude_quota_state = MagicMock(return_value=ClaudeLimits(
        five_hour=WindowInfo(utilization=0.90),
    ))

    tasks = decompose_goal("Build payment gateway", repo_root=tmp_path, token_master=tm)
    assert tasks[0]["engine"] == "hermes_worker"


def test_save_plan(tmp_path: Path):
    tasks = [{"id": "t1", "title": "Setup", "engine": "coder_worker", "depends_on": []}]
    saved = save_plan(tasks, "Test Goal", repo_root=tmp_path)
    assert saved.exists()

    now_file = tmp_path / "wcao" / "plans" / "now.md"
    assert now_file.exists()
    assert "**Active Goal:** Test Goal" in now_file.read_text()
    assert "t1" in now_file.read_text()

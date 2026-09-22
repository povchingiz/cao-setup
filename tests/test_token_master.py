"""Tests for run/cao_token_master.py — Proactive Token & Quota Awareness."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run.cao_limits import ClaudeLimits, WindowInfo
from run.cao_token_master import TokenMaster, TokenMasterDecision


def test_token_master_no_swap_when_under_quota():
    tm = TokenMaster(high_watermark=0.80)
    task = {"id": "t1", "engine": "claude_worker", "title": "Arch design"}

    limits = ClaudeLimits(
        five_hour=WindowInfo(utilization=0.35, resets_at=1800000000, status="allowed"),
        seven_day=WindowInfo(utilization=0.40, resets_at=1800000000, status="allowed"),
    )

    decision = tm.evaluate_task(task, claude_limits_override=limits)
    assert decision.swapped is False
    assert decision.selected_engine == "claude_worker"
    assert "Within quota" in decision.reason


def test_token_master_proactive_swap_on_high_utilization():
    tm = TokenMaster(high_watermark=0.80, reasoning_fallback="hermes_worker")
    task = {"id": "t2", "engine": "claude_worker", "title": "Hard refactor"}

    # Claude 5-hour utilization at 85%
    limits = ClaudeLimits(
        five_hour=WindowInfo(utilization=0.85, resets_at=1800000000, status="allowed"),
        seven_day=WindowInfo(utilization=0.50, resets_at=1800000000, status="allowed"),
    )

    decision = tm.evaluate_task(task, claude_limits_override=limits)
    assert decision.swapped is True
    assert decision.selected_engine == "hermes_worker"
    assert "Proactive quota swap" in decision.reason
    assert "85%" in decision.reason


def test_token_master_proactive_swap_when_blocked():
    tm = TokenMaster(reasoning_fallback="hermes_worker")
    task = {"id": "t3", "engine": "claude_worker", "title": "Critical fix"}

    limits = ClaudeLimits(
        blocked=True,
        blocked_window="five_hour",
        blocked_resets_at=1800005000,
    )

    decision = tm.evaluate_task(task, claude_limits_override=limits)
    assert decision.swapped is True
    assert decision.selected_engine == "hermes_worker"
    assert "rate limit blocked" in decision.reason


def test_token_master_large_context_advisory(tmp_path: Path):
    tm = TokenMaster()
    # Create 6 dummy files
    files = []
    for i in range(6):
        f = tmp_path / f"file_{i}.py"
        f.write_text("print('hello world')\n" * 50)
        files.append(f.name)

    task = {
        "id": "t4",
        "engine": "coder_worker",
        "title": "Cross-cutting refactor",
        "files": files,
    }

    decision = tm.evaluate_task(task, repo_root=tmp_path)
    assert decision.swapped is False
    assert len(decision.notices) >= 1
    assert "Large context detected" in decision.notices[0]
    assert "analyst_worker" in decision.notices[0]


def test_token_master_non_claude_engine_untouched():
    tm = TokenMaster()
    task = {"id": "t5", "engine": "coder_worker", "title": "Simple CRUD"}

    # Even if Claude is blocked, coder_worker is untouched
    limits = ClaudeLimits(blocked=True)
    decision = tm.evaluate_task(task, claude_limits_override=limits)
    assert decision.swapped is False
    assert decision.selected_engine == "coder_worker"


def test_autonomous_runner_token_master_integration(tmp_path: Path):
    from run.cao_auto import AutonomousRunner, CaoClient
    tasks_file = tmp_path / "tasks.json"
    import json
    tasks = [
        {"id": "t1", "engine": "claude_worker", "title": "Heavy Arch", "status": "pending"}
    ]
    tasks_file.write_text(json.dumps(tasks))

    runner = AutonomousRunner(tasks_file=tasks_file, dry_run=True)
    # Mock limits to force proactive swap
    mock_limits = ClaudeLimits(
        five_hour=WindowInfo(utilization=0.92, resets_at=1800000000, status="allowed"),
    )
    runner.token_master.get_claude_quota_state = MagicMock(return_value=mock_limits)

    runner._dispatch_task(tasks[0], tasks)

    assert tasks[0]["proactive_swap"] is True
    assert tasks[0]["engine"] == "hermes_worker"
    assert "92%" in tasks[0]["swap_reason"]


def test_token_master_marked_blocked_engine_swaps():
    tm = TokenMaster()
    # Mark codex_worker as blocked (e.g. after a runtime 429)
    tm.mark_engine_blocked("codex_worker", duration_seconds=3600, reason="OpenAI quota exhausted")

    task = {"id": "t_ui", "engine": "codex_worker", "title": "Build frontend"}
    decision = tm.evaluate_task(task)

    assert decision.swapped is True
    assert decision.selected_engine == "coder_worker"
    assert "OpenAI quota exhausted" in decision.reason


def test_token_master_initial_blocked_engines():
    # Test configuring initial blocked engines (e.g. user knows AGY or Codex has no quota)
    tm = TokenMaster(initial_blocked_engines=["antigravity_worker", "codex_worker"])

    task_agy = {"id": "t_audit", "engine": "antigravity_worker", "title": "Audit code"}
    decision = tm.evaluate_task(task_agy)
    assert decision.swapped is True
    assert decision.selected_engine == "coder_worker"
    assert "User configured quota exhaustion" in decision.reason


